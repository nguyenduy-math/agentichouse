# eval-v2 — RAGAS Evaluation for graphrag-assistant (OpenAI Judge)

Evaluates the `graphrag-assistant` RAG pipeline using [RAGAS](https://docs.ragas.io/) with **OpenAI as the judge LLM and embedding model**.

This is the successor to `eval/`, which used Gemini via an OpenAI-compatible proxy as a workaround for a known `instructor` library bug. `eval-v2` uses OpenAI natively through LangChain wrappers — no workaround needed.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11–3.13 | Tested on 3.12 / 3.13. **Do not use 3.14** — `pydantic-core` and other Rust-backed deps don't yet ship 3.14 wheels |
| OpenAI API key | Judge LLM + embeddings |
| graphrag-assistant backend | Running on `http://localhost:8000` (default) |

The backend must be up and indexed before running. See `rag-projects/graphrag-assistant/README.md` for startup instructions.

---

## Setup

### macOS / Linux

```bash
cd eval-v2

py -3.13 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

cp .env.example .env
# open .env and fill in your OPENAI_API_KEY
```

### Windows (PowerShell) — recreate with Python 3.13

If you already have a `.venv` created with Python 3.14, delete it first — Rust-backed dependencies like `pydantic-core` will fail to build on 3.14.

```powershell
cd eval-v2

# Remove the old venv if it exists
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue

# Create a new venv explicitly with Python 3.13
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Confirm — must print 3.13.x
python --version

python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

Copy-Item .env.example .env
# open .env and fill in your OPENAI_API_KEY
```

> **Check available Python versions** with `py -0`. If `-V:3.13` isn't listed, install Python 3.13 (64-bit) from [python.org](https://www.python.org/downloads/) and restart your terminal.
>
> If `Activate.ps1` is blocked by execution policy, run once per session:
>
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> ```

---

## Usage

```bash
# Full evaluation (queries the backend, then scores with OpenAI)
python graphrag_eval.py

# Test query collection only — no OpenAI scoring calls, no cost
python graphrag_eval.py --dry-run

# Use a more powerful judge model
python graphrag_eval.py --model gpt-4o
```

Results are saved as a timestamped CSV under `results/`, e.g. `results/graphrag_eval_20260525_153000.csv`.

---

## Configuration

All options can be set in `.env` or overridden via CLI flags.

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `OPENAI_JUDGE_MODEL` | `gpt-4o-mini` | Model used as RAGAS judge |
| `GRAPHRAG_API_URL` | `http://localhost:8000` | graphrag-assistant base URL |

CLI flags take precedence over `.env`:

| Flag | Description |
|---|---|
| `--model <name>` | Override the judge model (e.g. `gpt-4o`) |
| `--dry-run` | Skip RAGAS scoring; only collect and print RAG responses |

---

## Evaluation Metrics

Five RAGAS metrics are computed for each question:

| Metric | What it measures | Requires |
|---|---|---|
| `faithfulness` | Are all claims in the answer grounded in the retrieved contexts? | LLM |
| `answer_relevancy` | Is the answer on-topic and responsive to the question? | LLM + embeddings |
| `context_precision` | Are the most relevant chunks ranked at the top of retrieval? | LLM + reference |
| `context_recall` | Do the retrieved chunks cover all facts needed to answer correctly? | LLM + reference |
| `answer_correctness` | Does the answer match the reference (ground truth) answer? | LLM + embeddings |

All scores are in the range **[0, 1]** — higher is better.

---

## Question Set

Questions are loaded from:

```
rag-projects/graphrag-assistant/eval-sets/eval_questions.json
```

10 questions covering Vietnamese HR policy topics (remote work, leave, benefits, dress code, procedures), with difficulty levels easy / medium / hard and query types LOCAL / GLOBAL.

Each question includes:
- `question` — the user query sent to the backend
- `expected_answer_summary` — the reference answer used by RAGAS metrics that require ground truth (`context_recall`, `answer_correctness`)

---

## How It Works

```
eval_questions.json
      │
      ▼
[1] Query graphrag-assistant backend (POST /api/v1/session → POST /api/v1/chat)
      │  returns: reply (answer) + sources (retrieved contexts)
      ▼
[2] Build RAGAS EvaluationDataset (SingleTurnSample per question)
      │  fields: user_input, response, retrieved_contexts, reference
      ▼
[3] Run RAGAS evaluate() with OpenAI judge
      │  LLM:        ChatOpenAI (gpt-4o-mini)  via LangchainLLMWrapper
      │  Embeddings: OpenAIEmbeddings (text-embedding-3-small) via LangchainEmbeddingsWrapper
      ▼
[4] Save results CSV + print summary table
```

---

## Comparison with eval/ (v1)

| | eval/ (v1) | eval-v2 |
|---|---|---|
| Judge LLM | Gemini via OpenAI-compat proxy | Native OpenAI (`ChatOpenAI`) |
| Embeddings | `GoogleEmbeddings` (google-genai) | `OpenAIEmbeddings` (langchain-openai) |
| RAGAS scoring | Commented out (incomplete) | Fully wired up |
| CLI flags | None | `--dry-run`, `--model` |
| Retry config | None | `RunConfig(max_retries=3, timeout=120)` |

---

## Output Example

```
Loaded 10 questions from eval_questions.json

Step 1/3: Querying graphrag-assistant...
  [1/10] SQ-001: Một nhân viên vừa được tuyển và đang trong tháng đầ...
  [2/10] SQ-002: Nhân viên nữ vừa đi làm lại sau kỳ nghỉ thai sản, c...
  ...
Collected 10 responses.

Step 2/3: Building RAGAS dataset...
Step 3/3: Running RAGAS evaluation (judge: gpt-4o-mini)...

Results saved to: results/graphrag_eval_20260525_153000.csv

=== RAGAS Evaluation Summary (graphrag-assistant v2 / OpenAI judge) ===
Metric                          Score
----------------------------------------
faithfulness                   0.8750
answer_relevancy               0.9120
context_precision              0.7800
context_recall                 0.8200
answer_correctness             0.7650
========================================
```
