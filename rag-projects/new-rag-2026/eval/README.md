# eval/ — RAGAS Evaluation Suite for new-rag-2026

Evaluates the **new-rag-2026** multi-agent RAG pipeline using [RAGAS](https://docs.ragas.io/). Supports three judge LLM providers: OpenAI, Gemini, and SiliconFlow.

---

## What is RAGAS?

RAGAS (Retrieval Augmented Generation Assessment) is a framework for evaluating RAG systems without needing a human annotator for every question. It uses a judge LLM to score system responses along multiple dimensions, comparing answers against retrieved contexts and reference ground-truth answers.

### The 5 metrics

| Metric | What it measures | Requires |
|---|---|---|
| `faithfulness` | Are all claims in the answer grounded in the retrieved contexts? (hallucination detection) | LLM |
| `answer_relevancy` | Is the answer on-topic and responsive to the question? | LLM + embeddings |
| `context_precision` | Are the most relevant chunks ranked at the top of retrieval? | LLM + reference |
| `context_recall` | Do the retrieved chunks cover all facts needed to answer correctly? | LLM + reference |
| `answer_correctness` | Does the answer match the reference (ground truth) answer? | LLM + embeddings |

All scores are in **[0, 1]** — higher is better.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11–3.13 | **Do not use 3.14** — `pydantic-core` wheels not yet available |
| `OPENAI_API_KEY` | Always required (used for `text-embedding-3-small`) |
| Judge provider key | `GEMINI_API_KEY` or `SILICONFLOW_API_KEY` if not using OpenAI as judge |
| new-rag-2026 backend | Running on `http://localhost:8000` (default) |

---

## Setup

### Windows (PowerShell)

```powershell
cd new-rag-2026/eval

# Create venv with Python 3.13
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1

# If blocked by execution policy, run once per session:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

Copy-Item .env.example .env
# Open .env and fill in your API keys
```

### macOS / Linux

```bash
cd new-rag-2026/eval

py -3.13 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

cp .env.example .env
# Open .env and fill in your API keys
```

---

## Usage

### `eval_single.py` — Single-turn evaluation

Runs 20 standalone questions against the backend and scores each with all 5 RAGAS metrics.

```bash
# Full run with OpenAI judge (default)
python eval_single.py

# Use Gemini as judge (embeddings still use OpenAI)
python eval_single.py --judge-provider gemini

# Use SiliconFlow as judge
python eval_single.py --judge-provider siliconflow

# Override judge model
python eval_single.py --judge-model gpt-4o

# Collect responses only — no RAGAS scoring, no cost
python eval_single.py --dry-run
```

**Output:** timestamped CSV under `results/eval_single_YYYYMMDD_HHMMSS.csv`

Extra columns vs. eval-v2: `domain_keys`, `agent_count`, `query_type` — lets you filter results by which domain agents fired.

---

### `eval_multiturn.py` — Multi-turn conversation evaluation

Runs 5 conversation sets (4 turns each) as real sessions, reusing `session_id` across turns so the backend's conversation history is active. Cumulative contexts prevent memory-grounded claims from being penalised as ungrounded.

```bash
# Full run
python eval_multiturn.py

# Single set only (faster iteration)
python eval_multiturn.py --set CS-001

# Gemini judge
python eval_multiturn.py --judge-provider gemini

# Collect responses only
python eval_multiturn.py --dry-run
```

**Output:** `results/eval_multiturn_YYYYMMDD_HHMMSS.csv`

Prints a per-set summary table showing `answer_correctness` and `faithfulness` per conversation set — useful for spotting which conversation flow degrades most.

---

### `eval_per_domain.py` — Per-domain agent evaluation (new)

After each chat request, calls `GET /api/v1/chat/{session_id}/agent_trace` to retrieve each domain agent's individual answer, then evaluates those answers with RAGAS independently. This reveals **which domain agent is weakest** and guides targeted improvement.

```bash
# Evaluate all domains
python eval_per_domain.py

# Evaluate one domain only
python eval_per_domain.py --domain hr
python eval_per_domain.py --domain benefits

# Collect domain answers only, skip RAGAS
python eval_per_domain.py --dry-run
```

**Output:** `results/eval_per_domain_YYYYMMDD_HHMMSS.csv`

Prints a per-domain score table and highlights the weakest domain by `answer_correctness` with a recommended action (add documents / tune prompt).

> **Note on contexts:** The `/agent_trace` endpoint exposes each domain agent's answer but not its individual source chunks. The overall response sources are used as retrieved_contexts for all domain samples. `faithfulness` and `context_recall` scores are system-level approximations, not exact per-domain scores.

---

## CLI flags

All three scripts share these flags:

| Flag | Description | Default |
|---|---|---|
| `--judge-provider` | `openai` \| `gemini` \| `siliconflow` | `openai` (or `JUDGE_PROVIDER` env) |
| `--judge-model` | Override judge model name | Provider default (see below) |
| `--dry-run` | Collect responses only, skip RAGAS | off |

Per-provider judge model defaults:

| Provider | Default model |
|---|---|
| `openai` | `gpt-4o-mini` |
| `gemini` | `gemini-2.0-flash` |
| `siliconflow` | `deepseek-ai/DeepSeek-V3` |

Script-specific flags:

| Script | Flag | Description |
|---|---|---|
| `eval_multiturn.py` | `--set CS-001` | Evaluate a single conversation set |
| `eval_per_domain.py` | `--domain hr` | Evaluate questions for a specific domain |

---

## Configuration

All options can be set in `.env` or overridden via CLI flags. CLI flags take precedence.

| Variable | Default | Description |
|---|---|---|
| `NEW_RAG_API_URL` | `http://localhost:8000` | Backend base URL |
| `JUDGE_PROVIDER` | `openai` | Default judge provider |
| `OPENAI_API_KEY` | *(required)* | OpenAI key — always needed for embeddings |
| `OPENAI_JUDGE_MODEL` | `gpt-4o-mini` | OpenAI judge model override |
| `GEMINI_API_KEY` | *(if gemini)* | Gemini API key |
| `GEMINI_JUDGE_MODEL` | `gemini-2.0-flash` | Gemini judge model override |
| `SILICONFLOW_API_KEY` | *(if siliconflow)* | SiliconFlow API key |
| `SILICONFLOW_JUDGE_MODEL` | `deepseek-ai/DeepSeek-V3` | SiliconFlow judge model override |

---

## Output format

Each run produces a timestamped CSV with these columns:

**eval_single.py:**
```
id, domain, difficulty, query_type, domain_keys, agent_count,
user_input, response, retrieved_contexts, reference,
faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness
```

**eval_multiturn.py:**
```
set_id, turn, context_dependency, domain_keys, query_type, is_fallback,
user_input, response, retrieved_contexts, reference,
faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness
```

**eval_per_domain.py:**
```
domain_key, domain_name_vi, question_id, question_domain, difficulty, query_type,
user_input, response, retrieved_contexts, reference,
faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness
```

---

## Interpreting results

| Score range | Assessment |
|---|---|
| 0.85 – 1.00 | Excellent |
| 0.70 – 0.84 | Good — acceptable for production |
| 0.55 – 0.69 | Fair — room for improvement |
| < 0.55 | Poor — investigate retrieval or prompt quality |

**Diagnosing issues:**

- Low `faithfulness` → model is hallucinating beyond retrieved context; tighten system prompt or reduce LLM temperature
- Low `context_recall` → retrieval is missing relevant documents; add more documents or improve chunking
- Low `context_precision` → reranker is not ordering chunks well; tune rerank weights
- Low `answer_correctness` → answer content is wrong relative to ground truth; check if domain agent prompts are accurate
- Low score on specific domain in `eval_per_domain.py` → add more documents to that domain's index

---

## Comparison table: what each script tests

| | `eval_single.py` | `eval_multiturn.py` | `eval_per_domain.py` |
|---|---|---|---|
| Session type | Fresh per question | Shared per conversation set | Fresh per question |
| Conversation memory | No | Yes | No |
| Evaluates | Final synthesised answer | Each conversation turn | Each domain agent's answer |
| Best for | Overall pipeline quality | Memory / follow-up quality | Finding weakest domain |
| Agent trace used | No | No | Yes |
| Questions | 20 single questions | 5 sets × 4 turns | 20 single questions |
