# ReWOO Example 2: Document Calculation (Invoice PDF → Currency Conversion)

## 1. Overview

This example demonstrates a **fully sequential dependency chain** in ReWOO:

> **Query:** "Read the invoice PDF, extract the total amount, and convert it from JPY to VND."

Each step depends on the output of the previous one — there is no opportunity for parallelism. This contrasts with Example 1 (weather + currency), where the planner could issue independent tool calls in parallel and only join results at the solver.

| Dimension | Example 1 (Weather) | Example 2 (Doc Calc) |
|---|---|---|
| Dependency pattern | Parallel → join | Fully sequential |
| Tool types | API calls | PDF parse → LLM extraction → API call |
| Interesting challenge | Fan-out then merge | Passing structured output between steps |

Key concepts illustrated:
- **PDF parsing** as a ReWOO tool input
- **LLM-assisted extraction** as a mid-chain tool (a mini LLM call inside the worker)
- **Variable substitution** chaining `#E1 → #E2 → #E3`
- Worker resolving dependencies by scanning args for `#E` references before execution

---

## 2. Architecture — Data Flow

```
invoice.pdf
    │
    ▼
scan_pdf("data/invoice_sample.pdf")
    │
    ▼  #E1 = "Invoice #1042\nDate: 2024-01-15\nItem: Consulting  ¥15,000\nTotal: ¥15,000\n"
    │
    ▼
extract_total(#E1)          ← small LLM call (Claude Haiku) inside the tool
    │
    ▼  #E2 = "15000.0"
    │
    ▼
convert_currency(#E2, "JPY", "VND")   ← calls frankfurter.app API
    │
    ▼  #E3 = "2,415,000 VND"
    │
    ▼
Solver (Claude)
    │
    ▼
"The invoice total is ¥15,000 JPY, which equals approximately 2,415,000 VND."
```

The ReWOO plan produced by the Planner:

```
#E1 = scan_pdf["data/invoice_sample.pdf"]
#E2 = extract_total[#E1]
#E3 = convert_currency[#E2, JPY, VND]
```

---

## 3. Project Structure (additive)

Files to add on top of the existing layout. Do **not** remove or overwrite any existing files.

```
rewoo-llm/
├── tools/
│   ├── pdf.py           # NEW — scan_pdf implementation using pymupdf (fitz)
│   ├── extractor.py     # NEW — extract_total using a small LLM call
│   └── currency.py      # EXISTING — reused unchanged from example 1
├── examples/
│   ├── run_weather.py   # EXISTING
│   └── run_doc_calc.py  # NEW — entry point for this example
└── data/
    └── invoice_sample.pdf   # NEW — sample JPY invoice for testing
```

Existing files that are reused without modification:
- `models.py` — `Step`, `Plan`, `WorkerResult`
- `planner.py` — Planner class (prompt template changes; see Section 6)
- `worker.py` — Worker class (dependency resolution logic already handles sequential chains)
- `solver.py` — Solver class (prompt template changes; see Section 8)
- `tools/currency.py`

---

## 4. Data Models

**No new models are needed.** The existing models from `models.py` cover this example completely:

```python
@dataclass
class Step:
    variable: str        # e.g. "#E1"
    tool: str            # e.g. "scan_pdf"
    args: list[str]      # e.g. ["data/invoice_sample.pdf"]

@dataclass
class Plan:
    steps: list[Step]

@dataclass
class WorkerResult:
    variable: str
    result: str
```

The `WorkerResult.result` field is always a string. The `extract_total` tool returns a float internally but it is stringified before being stored (e.g. `"15000.0"`). The `convert_currency` tool receives `#E2` as a string arg and must cast it to float internally before calling the API.

---

## 5. Tool Specifications

### 5.1 `scan_pdf(file_path: str) -> str`

**File:** `tools/pdf.py`

**Purpose:** Extract all text from a PDF file and return it as a single string.

**Implementation strategy:**
- Prefer importing from `mcp_server/tools/pdf_tool.py` if that module exists in the project
- Otherwise, use `pymupdf` (`import fitz`) directly

```python
# tools/pdf.py

import os

def scan_pdf(file_path: str) -> str:
    """Extract text from a PDF file. Returns full text as a string."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF not found: {file_path}")

    try:
        import fitz  # pymupdf
    except ImportError:
        raise ImportError("pymupdf is required: pip install pymupdf")

    doc = fitz.open(file_path)
    if doc.page_count == 0:
        raise ValueError(f"PDF has no pages: {file_path}")

    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()

    text = "\n".join(pages).strip()
    if not text:
        raise ValueError(f"PDF produced no text (possibly scanned image): {file_path}")

    return text
```

**Error cases:**
- `FileNotFoundError` — path does not exist
- `ValueError` — PDF is empty or image-only (no extractable text layer)
- `ImportError` — pymupdf not installed

---

### 5.2 `extract_total(text: str) -> float`

**File:** `tools/extractor.py`

**Purpose:** Given raw text from a PDF, use a focused LLM call to extract the total invoice amount as a plain number.

**This tool makes its own LLM call** (Claude Haiku for cost efficiency). It is a "smart tool" — not pure computation, but a contained sub-call that the worker treats as a black box.

```python
# tools/extractor.py

import anthropic
import os

def extract_total(text: str) -> float:
    """Use an LLM to extract the total invoice amount from raw PDF text."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = (
        "Extract the total invoice amount as a plain number from the following text. "
        "Return ONLY the number — no currency symbols, no units, no commas, no extra words. "
        "Example valid responses: 15000 or 15000.0 or 1234.56\n\n"
        f"TEXT:\n{text}"
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=64,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    try:
        return float(raw.replace(",", ""))
    except ValueError:
        raise ValueError(
            f"extract_total: LLM returned non-numeric value: {raw!r}. "
            "Check that the PDF text contains a recognizable total amount."
        )
```

**Design notes:**
- Claude Haiku is used (not Sonnet/Opus) because this is a simple extraction, not reasoning
- The prompt explicitly forbids symbols and commas to make `float()` parsing reliable
- The `.replace(",", "")` guard handles cases like `"15,000"` that some models return despite instructions

---

### 5.3 `convert_currency(amount: float, from_currency: str, to_currency: str) -> str`

**File:** `tools/currency.py` — **reuse from Example 1, no changes needed**

The worker passes `#E2` (stored as the string `"15000.0"`) as the `amount` argument. The currency tool must accept either `float` or `str` and cast internally:

```python
amount = float(amount)  # safe because #E2 is always "15000.0"
```

**API call:**
```
GET https://api.frankfurter.app/latest?from=JPY&to=VND&amount=15000
```

**Returns:** `"2,415,000 VND"` (formatted string)

---

## 6. Planner Prompt

The Planner receives the user's query and outputs a plan using `#E` variable notation. For this example, the system prompt instructs the LLM to produce a sequential chain.

```python
SYSTEM_PROMPT = """You are a planning agent. Given a task, produce a step-by-step plan using the tools below.
Each step has the form:
  #En = tool_name[arg1, arg2, ...]

You may reference previous step results as arguments using their variable names (e.g. #E1, #E2).

Available tools:
- scan_pdf[file_path] — extracts all text from a PDF file
- extract_total[text] — extracts the total invoice amount as a number from raw text
- convert_currency[amount, from_currency, to_currency] — converts a currency amount using live rates

Rules:
- Only output the plan, one step per line, no explanation
- Use the exact tool names above
- Quote string literals with double quotes
- Do not quote variable references like #E1
"""

USER_PROMPT = "Task: {query}"
```

**Expected planner output for this query:**

```
#E1 = scan_pdf["data/invoice_sample.pdf"]
#E2 = extract_total[#E1]
#E3 = convert_currency[#E2, "JPY", "VND"]
```

---

## 7. Worker: Dependency Resolution

The worker iterates through `Plan.steps` in order. Before executing a step, it scans each argument for `#E` references and substitutes the stored result.

```python
def resolve_args(args: list[str], results: dict[str, str]) -> list[str]:
    """Replace any #En references in args with their computed values."""
    resolved = []
    for arg in args:
        if arg.startswith("#E") and arg in results:
            resolved.append(results[arg])
        else:
            resolved.append(arg)
    return resolved
```

**Execution trace for this example:**

| Step | Raw args | Resolved args | Runs after |
|---|---|---|---|
| #E1 | `["data/invoice_sample.pdf"]` | `["data/invoice_sample.pdf"]` | — |
| #E2 | `["#E1"]` | `["<full PDF text>"]` | #E1 |
| #E3 | `["#E2", "JPY", "VND"]` | `["15000.0", "JPY", "VND"]` | #E2 |

Because every step depends on the previous one, the worker naturally executes them sequentially — there are no independent steps to parallelize. The same worker code that handles Example 1's parallel steps handles this sequential chain correctly, because it resolves dependencies before each call.

---

## 8. Solver Prompt

The solver receives the original question plus all `WorkerResult` values and synthesizes a natural-language answer.

```python
SOLVER_SYSTEM = """You are a helpful assistant. Given a question and a set of intermediate results
computed by specialized tools, provide a clear, concise final answer to the question.
Do not repeat the intermediate steps — just answer the question directly."""

SOLVER_USER = """Question: {query}

Intermediate results:
#E1 (PDF text, truncated): {e1_truncated}
#E2 (extracted total): {e2}
#E3 (converted amount): {e3}

Answer:"""
```

**Note on #E1 truncation:** The raw PDF text in `#E1` may be long. Truncate to ~500 characters in the solver prompt to avoid wasting tokens, since the solver only needs the final values (`#E2`, `#E3`) to answer.

```python
e1_truncated = results["#E1"][:500] + ("..." if len(results["#E1"]) > 500 else "")
```

---

## 9. Sample Invoice — `data/invoice_sample.pdf`

The sample PDF should contain a simple Japanese yen invoice that a human or LLM can read unambiguously. **Suggested content:**

```
INVOICE

Invoice #:    1042
Date:         2024-01-15
Vendor:       Tanaka Consulting K.K.
Client:       Acme Corp.

-------------------------------------------------
Description                        Amount (JPY)
-------------------------------------------------
Software consulting (Jan 2024)      ¥12,000
Documentation review                 ¥3,000
-------------------------------------------------
TOTAL                               ¥15,000
-------------------------------------------------

Payment due within 30 days.
Bank: Mitsubishi UFJ Bank
Account: 1234567
```

**Key requirements for the PDF:**
- The word "TOTAL" should appear clearly before the number
- The total must be `15000` (matches the expected console output)
- Use a real text layer (not a scanned image) so `pymupdf` can extract it without OCR

**How to generate it for testing:**

```python
# scripts/generate_invoice.py
import fitz  # pymupdf

doc = fitz.open()
page = doc.new_page()
content = """INVOICE

Invoice #:    1042
Date:         2024-01-15
Vendor:       Tanaka Consulting K.K.
Client:       Acme Corp.

Description                        Amount (JPY)
Software consulting (Jan 2024)      12,000
Documentation review                 3,000
TOTAL                               15,000

Payment due within 30 days.
"""
page.insert_text((72, 72), content, fontsize=11)
doc.save("data/invoice_sample.pdf")
doc.close()
print("Saved data/invoice_sample.pdf")
```

---

## 10. Expected Console Output

Running `python examples/run_doc_calc.py` should produce:

```
[Planner] Generating plan...
Plan:
  #E1 = scan_pdf["data/invoice_sample.pdf"]
  #E2 = extract_total[#E1]
  #E3 = convert_currency[#E2, JPY, VND]

[Worker] Executing #E1: scan_pdf...
  → #E1 = "Invoice #1042\nDate: 2024-01-15\nVendor: Tanaka Consulting K.K.\n..."

[Worker] Executing #E2: extract_total...
  → #E2 = "15000.0"

[Worker] Executing #E3: convert_currency...
  → #E3 = "2,415,000 VND"

[Solver] Generating final answer...

Answer: The invoice total is ¥15,000 JPY, which equals approximately 2,415,000 VND.
```

**Notes:**
- The VND amount will vary with live exchange rates; `2,415,000` is approximate
- `#E1` is printed truncated in the console; the worker stores the full text

---

## 11. Implementation Order

1. **Add `pymupdf` to `requirements.txt`** — append `pymupdf` (do not overwrite existing entries)

2. **Add `ANTHROPIC_API_KEY` to `.env.example`** — if `.env.example` doesn't exist, create it; if it does, only add missing keys

3. **Create `data/` directory** and run `scripts/generate_invoice.py` to produce `invoice_sample.pdf`

4. **Implement `tools/pdf.py`** — `scan_pdf` using `fitz`; include error handling for missing file, empty PDF, and missing library

5. **Implement `tools/extractor.py`** — `extract_total` using Claude Haiku; include the float-parsing guard

6. **Verify `tools/currency.py`** — confirm it accepts a string `amount` arg and casts to float internally; patch if needed

7. **Add the tool registry entry** in `worker.py` (or wherever tools are registered) for `scan_pdf` and `extract_total`

8. **Create `examples/run_doc_calc.py`** — wire together Planner → Worker → Solver with this example's query and prompt templates; print formatted output matching Section 10

9. **Smoke test** — run `python examples/run_doc_calc.py` end-to-end and confirm the answer mentions the correct JPY total and a VND equivalent

10. **Update `README.md`** (if one exists) — add a one-line entry for this example under the examples section
