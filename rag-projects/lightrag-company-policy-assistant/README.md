# Business Policy Assistant

A multi-agent RAG system that allows employees to ask questions in Vietnamese about all company policies. **10 expert agents** — each agent equipped with the retrieval tool best suited for their document type — are orchestrated by an OrchestratorAgent using Gemini to classify questions and synthesize results.

```
Employee Question → OrchestratorAgent (domain classification)
  ├── 1 domain    → expert agent → direct answer
  └── many domains → fan-out in parallel → synthesized answer
```

---

## Two Retrieval Tools

| Tool | Strengths | Used for |
|------|-----------|----------|
| **LightRAG** | Knowledge graph + vector hybrid. Finds relationships between entities (roles, departments, policies) across multiple documents. | HR policies, procedures, employee handbook, training |
| **PageIndex Cloud** | Upload PDF to cloud → download knowledge tree JSON locally → Gemini navigates tree by node_id → reads `node.text` + original PDF text → answer with precise page citations. | Benefits & compensation — need exact page numbers and amounts |

---

## 10 Expert Agents

| Agent | Domain Key | Tool | Folder | Best for |
|---------|-----------|---------|---------|-----------------|
| `HRPolicyAgent` | `HR_POLICY` | LightRAG (hybrid) | `hr_policies/` | Employment contracts, vacation, working hours, performance reviews |
| `BenefitsAgent` | `BENEFITS` | PageIndex Cloud | `benefits/` | Salary, insurance, retirement, allowances — page citations from cloud knowledge tree |
| `ConductAgent` | `CONDUCT` | LightRAG (hybrid) | `conduct/` | Code of conduct, dress code, discipline, role–rule–penalty relationships |
| `ProceduresAgent` | `PROCEDURES` | LightRAG (hybrid) | `procedures/` | Step-by-step procedures, approval chains, onboarding |
| `HandbookAgent` | `HANDBOOK` | LightRAG (global) | `handbooks/` | Company culture, mission, general new employee information |
| `MedicalAgent` | `MEDICAL` | LightRAG (hybrid) | `medical/` | Health insurance, hospital–service–reimbursement relationships |
| `ITSecurityAgent` | `IT_SECURITY` | LightRAG (hybrid) | `it_security/` | Device usage, passwords, data security, system–access relationships |
| `ComplianceAgent` | `COMPLIANCE` | LightRAG (hybrid) | `compliance/` | Labor law, PDPA/GDPR, anti-corruption, obligation–penalty relationships |
| `FinanceAgent` | `FINANCE` | LightRAG (hybrid) | `finance/` | Expense limits, reimbursements, category–approver–deadline relationships |
| `TrainingAgent` | `TRAINING` | LightRAG (hybrid) | `training/` | Career paths, training programs, scholarships, certifications |

---

## Project Structure

```
lightrag-company-policy-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app + lifespan (init all 10 agents)
│   │   ├── config.py                  # Pydantic-settings (.env)
│   │   ├── schemas.py                 # Request/response models
│   │   ├── ingestion.py               # PDF / DOCX / MD / TXT extraction
│   │   ├── agents/
│   │   │   ├── base_agent.py          # BaseAgent ABC
│   │   │   ├── orchestrator.py        # OrchestratorAgent: classify → route → synthesize
│   │   │   ├── hr_policy_agent.py     # LightRAG — HR policies
│   │   │   ├── benefits_agent.py      # PageIndex Cloud — Benefits & compensation
│   │   │   ├── conduct_agent.py       # LightRAG — Code of conduct
│   │   │   ├── procedures_agent.py    # LightRAG — Procedures & processes
│   │   │   ├── handbook_agent.py      # LightRAG — Employee handbook
│   │   │   ├── medical_agent.py       # LightRAG — Medical policy
│   │   │   ├── it_security_agent.py   # LightRAG — IT & Security
│   │   │   ├── compliance_agent.py    # LightRAG — Compliance & Legal
│   │   │   ├── finance_agent.py       # LightRAG — Finance policy
│   │   │   └── training_agent.py      # LightRAG — Training & Development
│   │   ├── services/
│   │   │   ├── lightrag_service.py         # LightRAGService (per-domain instance)
│   │   │   ├── pageindex_cloud_service.py  # upload PDF → cloud → download tree JSON locally
│   │   │   └── search_service.py           # navigate tree + read node.text + PDF → answer
│   │   └── routers/
│   │       ├── health.py              # GET /health (per-agent status)
│   │       ├── ingest.py              # POST /ingest, /ingest/upload
│   │       ├── chat.py                # POST /chat
│   │       └── admin.py               # GET /admin/stats, /admin/agents, POST /admin/reindex
│   ├── data/documents/
│   │   ├── hr_policies/               # HR policies, contracts, vacation policies
│   │   ├── benefits/                  # Benefits, salary, retirement, allowances
│   │   ├── conduct/                   # Code of conduct, ethics, discipline
│   │   ├── procedures/                # SOP, onboarding process, request guidelines
│   │   ├── handbooks/                 # Employee handbook, company culture
│   │   ├── medical/                   # Medical policy, health insurance, hospital list
│   │   ├── it_security/               # IT policy, data security, device regulations
│   │   ├── compliance/                # Labor law, PDPA, anti-corruption
│   │   ├── finance/                   # Finance policy, expense limits, reimbursements
│   │   └── training/                  # Training programs, career paths, scholarships
│   ├── requirements.txt
│   └── .env.example
├── frontend/                          # React + Vite SPA
│   └── src/
│       ├── App.jsx                    # Agent status chips in header
│       ├── api.js
│       └── components/
│           ├── ChatBox.jsx            # Upload bar + chat messages
│           └── Message.jsx            # Domain badges + citation badges
├── docker-compose.yml                 # Neo4j + backend
└── HLD.md                            # Architecture diagram
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker (for Neo4j)
- Google Gemini API key
- PageIndex API key (from [dash.pageindex.ai/api-keys](https://dash.pageindex.ai/api-keys))

---

## Setup

### 1. Start Neo4j

```bash
docker-compose up neo4j -d
```

Wait until Neo4j is healthy (check at `http://localhost:7474`).

### 2. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt

# PageIndex Cloud SDK:
pip install -U pageindex
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```ini
GEMINI_API_KEY=your-key-here
NEO4J_PASSWORD=please-change-me        # must match docker-compose.yml
PAGEINDEX_API_KEY=your-pi-key-here     # from dash.pageindex.ai/api-keys
```

### 4. Start the backend

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On startup, all ten domain agents initialize. Nine LightRAG agents connect to Neo4j and set up their storage directories. The one PageIndex Cloud agent (BENEFITS) loads its local tree registry — uploaded PDFs have their tree JSONs cached in `rag_storage/pageindex/benefits/`.

### 5. Start the frontend (dev)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

---

## Usage

### Upload Documents

Use the upload bar at the top of the chat window. Select the domain corresponding to your document and click **Upload Document**.

| Domain | Documents to Upload |
|--------|---------------------|
| HR Policies | Vacation policies, employment contract templates, working hours regulations |
| Benefits & Compensation | Salary scales, health insurance plans, bonus policies |
| Code of Conduct | Code of conduct, anti-harassment policy, dress code regulations |
| Procedures & Processes | Onboarding procedures, reimbursement guidelines, approval workflows |
| Employee Handbook | Employee handbook, company values, office guidelines |
| Medical Policy | Health insurance contracts, hospital list, medical procedures |
| IT & Security | IT security policy, device usage regulations, password guidelines |
| Compliance & Legal | Labor law regulations, data protection policy (PDPA), anti-corruption rules |
| Finance Policy | Financial regulations, expense limits, business travel reimbursement process |
| Training & Development | Training programs, career paths, scholarship and certification policies |

Or bulk ingest a directory via API:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"folder": null}'
```

### Ask Questions

Type any question in Vietnamese. The OrchestratorAgent automatically classifies and routes to the correct expert agent.

**Single-domain examples:**

| Question | Agent | Tool |
|----------|-------|------|
| "How many annual vacation days do I get?" | BENEFITS | PageIndex Cloud → navigate tree + page citations |
| "Can contractors wear casual Friday?" | CONDUCT | LightRAG → entity graph |
| "How does vacation policy relate to remote work?" | HR_POLICY | LightRAG → entity graph |
| "What are the steps to submit a reimbursement request?" | PROCEDURES | LightRAG → graph traversal |
| "Which hospitals are covered by my health insurance?" | MEDICAL | LightRAG → entity graph |
| "Can I install personal software on my work computer?" | IT_SECURITY | LightRAG → entity graph |
| "What is the domestic business travel expense limit?" | FINANCE | LightRAG → entity graph |
| "What are the requirements to be sent for professional certification?" | TRAINING | LightRAG → entity relationships |

**Multi-domain example:**

> "Are part-time employees eligible for health insurance, and how many sick days are they entitled to?"

→ Consults `HR_POLICY` + `BENEFITS` + `MEDICAL` in parallel → synthesized answer with page citations from benefits documents and graph context from HR policies.

---

## API Reference

### `GET /api/health`

Returns per-agent readiness.

```json
{
  "status": "degraded",
  "agents": {
    "HR_POLICY":   { "ready": true,  "engine_type": "lightrag",   "indexed_docs": 3 },
    "BENEFITS":    { "ready": true,  "engine_type": "pageindex",  "indexed_docs": 1 },
    "CONDUCT":     { "ready": false, "engine_type": "lightrag",   "indexed_docs": 0 },
    "PROCEDURES":  { "ready": true,  "engine_type": "lightrag",   "indexed_docs": 2 },
    "HANDBOOK":    { "ready": false, "engine_type": "lightrag",   "indexed_docs": 0 }
    // … all 10 domains (MEDICAL, IT_SECURITY, COMPLIANCE, FINANCE, TRAINING) appear here too
  },
  "neo4j_connected": true,
  "llm_model": "gemini-2.5-flash",
  "embedding_model": "gemini-embedding-001"
}
```

### `POST /api/ingest/upload`

Multipart form upload. Fields: `files[]` (one or more files) + `doc_type` (string).

```bash
curl -X POST http://localhost:8000/api/ingest/upload \
  -F "files=@benefits_guide.pdf" \
  -F "doc_type=benefits"
```

Valid `doc_type` values: `hr_policies`, `benefits`, `conduct`, `procedures`, `handbooks`, `medical`, `it_security`, `compliance`, `finance`, `training`.

> The full list is derived from a single source of truth — [`backend/app/domains.py`](backend/app/domains.py). Adding a domain there (and registering its agent in `main.py`) updates the API schema, classifier prompt, and ingest map together.

### `POST /api/chat`

```json
// Request
{
  "message": "How many sick days do junior engineers get?",
  "history": [],
  "history_turns": 3
}

// Response
{
  "answer": "Junior engineers receive 12 sick days per year...",
  "domains_consulted": ["BENEFITS"],
  "citations": [
    { "document": "benefits_guide.pdf", "page": 4, "section": "sick leave eligibility", "domain": "BENEFITS" }
  ],
  // Populated for LightRAG-backed domains (all except BENEFITS)
  // with the knowledge-graph entities behind the answer; empty for the PageIndex domain.
  "entities": ["Nghỉ ốm", "Kỹ sư", "Phòng Nhân sự"],
  "history": [
    { "role": "user",      "content": "How many sick days do junior engineers get?" },
    { "role": "assistant", "content": "Junior engineers receive 12 sick days per year..." }
  ]
}
```

### `GET /api/admin/stats`

Returns indexed document counts per agent.

### `POST /api/admin/reindex`

Triggers a background re-index of all files in `data/documents/`.

---

## Storage Layout

```
backend/
├── data/documents/         ← source files (one sub-folder per domain)
└── rag_storage/
    ├── lightrag/
    │   ├── hr_policy/      ← LightRAG vector + KV store (HR_POLICY)
    │   ├── procedures/     ← LightRAG vector + KV store (PROCEDURES)
    │   ├── handbook/       ← LightRAG vector + KV store (HANDBOOK)
    │   ├── training/       ← LightRAG vector + KV store (TRAINING)
    │   ├── conduct/        ← LightRAG vector + KV store (CONDUCT)
    │   ├── medical/        ← LightRAG vector + KV store (MEDICAL)
    │   ├── it_security/    ← LightRAG vector + KV store (IT_SECURITY)
    │   ├── compliance/     ← LightRAG vector + KV store (COMPLIANCE)
    │   └── finance/        ← LightRAG vector + KV store (FINANCE)
    └── pageindex/
        └── benefits/       ← registry.json + {doc_id}.json knowledge tree (BENEFITS cloud)
```

Neo4j stores the entity/relation graphs for all LightRAG agents (shared instance, isolated by `working_dir`).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.5 Flash |
| Embeddings | gemini-embedding-001 (1536d) |
| Graph RAG | [LightRAG](https://github.com/HKUDS/LightRAG) |
| Vectorless RAG | [PageIndex Cloud](https://pageindex.ai) (tree download + Gemini navigation) |
| Graph DB | Neo4j 5 |
| Backend | FastAPI + Uvicorn |
| Config | Pydantic-settings |
| Frontend | React 18 + Vite |
