# Insurance Guide Virtual Assistant

A Vietnamese-market insurance assistant with two modes — a conversational chat interface and a structured claim form page — backed by a FastAPI backend, React + Vite frontend, and an optional MCP server for PDF extraction and currency conversion.

| Mode | Description |
|---|---|
| **Khai thác bảo hiểm** | Guides users through filing a BHYT or commercial insurance claim |
| **Tư vấn gói bảo hiểm** | Collects a health profile and recommends 2–3 matching insurance packages |

Users pick a mode on the welcome screen; the assistant guides them step-by-step in natural Vietnamese.

---

## Features

- **Two modes, one interface** — mode selector before the conversation starts
- **Phase-based flow** — `identifying → collecting → confirming → complete`; each phase has its own response style
- **Option chips at decision points** — the assistant suggests 2–3 quick choices (gender, job type, benefit priority…) instead of open-ended questions
- **Confirmation gate** — the `confirming` phase shows all collected data and asks: confirm / edit / restart
- **Correction detection** — when users amend earlier info, the assistant confirms the change before continuing
- **Structured extraction** — Gemini `response_schema` parses dates/amounts from natural language
- **Catalog-grounded recommendations** — packages are selected only from a local `packages_catalog.json`; Gemini never invents insurers or premiums
- **Real-time progress bar** — % completion by claim type / mode
- **Downloadable results** — claim proposal or insurance recommendations as JSON

### Claim Form page (`/claim`)

- Vietnamese UI with claim type selector (ngoại trú / nội trú / bảo hiểm thương mại)
- Conditional fields that appear based on the selected claim type
- Live progress bar
- Submit → summary/review card
- **Floating chat widget** — bottom-right chat bubble that connects to the existing `/chat` backend; when the bot returns `collected` fields they are synced into the form automatically
- **PDF upload in chat** — paperclip button lets users upload a claim-related PDF; extracted fields are shown in a confirmation card; clicking "Xác nhận điền form" populates the form

---

## Architecture

### Overview

```
Browser (React SPA)
    │
    ├─ / (Chat interface)
    │   ├─ ModeSelector ──► POST /api/session/new { mode }
    │   └─ Chat ──────────► POST /api/chat { session_id, message }
    │
    └─ /claim (Claim Form page)
        ├─ ClaimForm ─────────────────────────── standalone form
        └─ FloatingChat ──► POST /api/chat      chat widget
                        ──► POST /api/upload-pdf  PDF upload
                              │
                    ┌─────────┴──────────┐
              mode=claim_filing    mode=recommendation
                    │                    │
               agent.py          advisor_agent.py
                    │                    │
                    │            catalog.py (filter packages)
                    │                    │
            Gemini API           Gemini API
         (extract + guide)   (extract + guide + recommend)
```

### Extract → Guide loop (shared by both modes)

```
User message
    │
    ▼
[Call 1: Extract]  response_schema=<DataModel>  temp=0.0
    │   Only returns fields explicitly mentioned; rest = null
    ▼
Merge into session state
    │
    ├─ Missing fields? ──► [Call 2: Guide] temp=0.3  ──► Next question + option chips
    │
    └─ All fields present? ──► confirming phase (text summary + 3 option chips)
                                    │
                          User confirms
                                    │
                              [Call 3: Result]
                          claim: summary text   recommend: response_schema=RecommendationOutput
```

### Session state machine (`SessionPhase`)

```
                    ┌─────────────┐
                    │  identifying │  (claim flow only — outpatient/inpatient/commercial)
                    └──────┬──────┘
                           │ claim_type determined
                           ▼
[mode=recommendation] ──► collecting ◄── [edit from confirming]
                           │
                all required fields present
                           │
                           ▼
                      confirming  ──► chips: [Confirm | Edit | Restart]
                           │
                 user confirms ("đúng", "1", "xác nhận")
                           │
                           ▼
                       complete  ──► result cached, subsequent messages skipped
```

---

## Claim Filing Mode

### Required fields by claim type

| Type | Required fields |
|---|---|
| Outpatient (`outpatient`) | Full name, DOB, BHXH code, facility, visit date, diagnosis, total cost |
| Inpatient (`inpatient`) | + Admission date, discharge date, out-of-pocket amount |
| Commercial (`private`) | Replaces BHXH code with contract number; adds event date, bank account |

### Output

- Vietnamese-language claim summary
- `ProposalCard` — data table + "Download JSON" button

---

## Insurance Recommendation Mode

### Health profile fields

| Field | Required | Option chips |
|---|---|---|
| Age | Yes | — |
| Gender | Yes | Nam / Nữ |
| Job type | Yes | Văn phòng / Ngoài trời / Lao động nặng |
| Pre-existing conditions | No | — |
| Smoker | Yes | Có hút thuốc / Không hút thuốc |
| Monthly budget (VND) | Yes | — |
| Number of people to insure | Yes | — |
| Benefit priority | Yes | Nội trú / Ngoại trú / Bệnh hiểm nghèo / Tai nạn / Nhân thọ |

### How recommendations work (catalog grounding)

The assistant relies on a local `backend/app/packages_catalog.json` (12 packages from fictional insurers: An Tín, Trường Phúc Life, Minh An Life, Việt Khang Life, Hồng Ân…):

1. **Load** — `load_catalog()` reads and caches JSON (`lru_cache`)
2. **Filter** — `filter_by_profile()` applies hard conditions (age, smoking, excluded jobs) → scores by benefit priority + budget → keeps top 6
3. **Format** — `format_for_prompt()` selects the best-fit tier, builds prompt text
4. **Constraint** — `RECOMMENDATION_SYSTEM` forbids inventing packages outside the catalog; `response_schema=RecommendationOutput` locks the output structure
5. **Fallback** — if filtering yields nothing, use the first 6 catalog entries (logged as a warning)

### Output

```json
{
  "recommendations": [
    {
      "rank": 1,
      "package_type": "Bảo hiểm sức khỏe toàn diện",
      "insurer_examples": ["An Tín", "Trường Phúc Life"],
      "estimated_premium_range": "500.000 – 1.500.000 VNĐ/tháng",
      "coverage_highlights": ["Nội trú không giới hạn", "Ngoại trú 30 lần/năm"],
      "why_suitable": "Phù hợp vì...",
      "key_considerations": ["Chú ý điều khoản loại trừ bệnh nền"]
    }
  ]
}
```

`RecommendationCard` renders each package with rank-based colours and a "Download JSON" button.

---

## PDF Upload Flow

Users can upload a PDF (e.g. a hospital invoice or existing policy) inside the floating chat widget on the `/claim` page.

```
User clicks paperclip → selects PDF
    │
    ▼
POST /api/upload-pdf  (multipart/form-data)
    │
    ▼
backend extracts text via mcp_server/tools/pdf_tool.py (PyPDFLoader)
    │
    ▼
Extracted text stored in session as pdf_context
    │
    ▼
On every subsequent /chat turn, pdf_context is injected into the agent prompt
    │
    ▼
Agent returns collected fields → FloatingChat renders ConfirmationCard
    │
    ├─ User clicks "Xác nhận điền form" → form fields auto-populated
    └─ User clicks "Bỏ qua" → card dismissed, chat continues
```

---

## MCP Server

A standalone Python MCP server (`mcp_server/`) built with LangChain + FastMCP. It exposes two tools:

| Tool | Description |
|---|---|
| `scan_pdf(file_path)` | Extracts text from a PDF using PyPDFLoader |
| `convert_currency(amount, from_currency, to_currency)` | Live exchange rates via frankfurter.app |

The backend imports `pdf_tool.py` directly for the `/upload-pdf` endpoint — no running MCP server required for that use case. The MCP server is for external integrations (e.g. Claude Desktop).

See [`mcp_server/README.md`](mcp_server/README.md) for full setup and tool reference.

---

## Project Structure

```
insurance-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI lifespan, CORS, router registration
│   │   ├── config.py                # Pydantic-settings (reads from .env)
│   │   ├── schemas.py               # All models: ClaimData, HealthProfile, SessionState, …
│   │   ├── claim_schema.py          # REQUIRED_FIELDS + FIELD_META for claim flow
│   │   ├── health_profile_schema.py # REQUIRED_PROFILE_FIELDS + PROFILE_FIELD_META + FIELD_CHIPS
│   │   ├── session_store.py         # In-memory store, asyncio.Lock, auto TTL
│   │   ├── agent.py                 # Claim flow: extract → guide → proposal (phase dispatcher)
│   │   ├── advisor_agent.py         # Recommendation flow: extract → guide → recommend
│   │   ├── catalog.py               # Filter/score packages by profile + format for prompt
│   │   ├── packages_catalog.json    # 12-package insurance catalog (recommendation source)
│   │   ├── prompts.py               # All system prompts and prompt builders
│   │   └── routers/
│   │       ├── chat.py              # POST /chat (mode dispatch) + POST /upload-pdf
│   │       ├── session.py           # POST /session/new { mode }, DELETE /session/{id}
│   │       └── health.py            # GET /health
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # State management, route configuration
│   │   ├── api.js                   # newSession(mode), sendMessage(), uploadPdf()
│   │   ├── pages/
│   │   │   └── ClaimPage.jsx        # /claim route — wraps ClaimForm + FloatingChat
│   │   └── components/
│   │       ├── ModeSelector.jsx     # Mode selection cards
│   │       ├── ChatWindow.jsx       # Message list + auto-scroll
│   │       ├── MessageBubble.jsx    # User / assistant bubbles
│   │       ├── OptionChips.jsx      # Quick-choice button row
│   │       ├── ProgressBar.jsx      # Completion % bar
│   │       ├── ProposalCard.jsx     # Claim proposal table + download JSON
│   │       ├── RecommendationCard.jsx # Recommended packages + download JSON
│   │       ├── ClaimForm.jsx        # Structured claim form with conditional fields
│   │       └── FloatingChat.jsx     # Floating chat bubble + PDF upload + ConfirmationCard
│   ├── index.html
│   ├── package.json
│   └── vite.config.js               # Dev proxy /api → localhost:8002
└── mcp_server/
    ├── server.py                    # FastMCP server entry point
    ├── tools/
    │   ├── pdf_tool.py              # scan_pdf tool (PyPDFLoader)
    │   └── currency_tool.py         # convert_currency tool (frankfurter.app)
    ├── requirements.txt
    └── README.md
```

---

## Getting Started

### Requirements

- Python 3.11+
- Node.js 18+
- LLM API key: Google Gemini ([get one](https://aistudio.google.com/app/apikey)) **or** SiliconFlow ([get one](https://cloud.siliconflow.cn))

### Backend

```bash
cd labs/insurance-assistant/backend

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env: set LLM_PROVIDER and fill in the matching API key

uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Interactive API docs: [http://localhost:8002/docs](http://localhost:8002/docs)

### Frontend

```bash
cd labs/insurance-assistant/frontend

npm install
npm run dev
# Open http://localhost:5173
```

The `/claim` route is at [http://localhost:5173/claim](http://localhost:5173/claim).

> In production (`npm run build`), FastAPI serves the SPA directly — no separate frontend server needed.

### MCP Server (optional)

Only needed for Claude Desktop integration. The backend uses `pdf_tool.py` directly and does not require the MCP server to be running.

```bash
cd labs/insurance-assistant/mcp_server

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python server.py
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | No | `gemini` (default) or `siliconflow` |
| `GEMINI_API_KEY` | When using Gemini | Google Gemini API key |
| `GEMINI_LLM_MODEL` | No | Default: `gemini-2.5-flash` |
| `SILICONFLOW_API_KEY` | When using SiliconFlow | SiliconFlow API key |
| `SILICONFLOW_BASE_URL` | No | Default: `https://api.siliconflow.cn/v1` |
| `SILICONFLOW_LLM_MODEL` | No | Default: `Qwen/Qwen2.5-72B-Instruct` |
| `SESSION_TTL_MINUTES` | No | Session lifetime (default: 60 min) |

The backend supports both providers through the same interface (`app/llm.py`). Switch by changing `LLM_PROVIDER` and filling in the matching key — no code changes needed. Only one provider is active at a time; a missing key produces a clear error.

---

## API Reference

### `POST /api/session/new`

```json
// Request
{ "mode": "claim_filing" }   // or "recommendation"

// Response
{ "session_id": "uuid-string" }
```

### `POST /api/chat`

```json
// Request
{ "session_id": "uuid-string", "message": "Tôi nhập viện điều trị tuần trước" }

// Response
{
  "session_id": "uuid-string",
  "reply": "Bạn điều trị tại bệnh viện nào ạ?",
  "collected": { "claim_type": "inpatient", "name": null },
  "health_profile": {},
  "proposal": null,
  "recommendation": null,
  "is_complete": false,
  "progress_pct": 22,
  "session_phase": "collecting",
  "options": null
}
```

### `POST /api/upload-pdf`

Multipart form upload (`file` field). Returns extracted text and any fields the agent detected:

```json
{
  "text": "Extracted PDF text...",
  "collected": { "name": "Nguyễn Văn A", "diagnosis": "..." }
}
```

### `DELETE /api/session/{session_id}`

Deletes a session.

### `GET /api/health`

Service health check.

---

## Extending the Project

### Add a health profile field

1. Add the field to `HealthProfile` in `backend/app/schemas.py`
2. Add metadata to `PROFILE_FIELD_META` in `backend/app/health_profile_schema.py`
3. Add to `REQUIRED_PROFILE_FIELDS` if mandatory
4. Add `FIELD_CHIPS` if you want quick-choice buttons

### Add a new claim type

1. Add a value to the `ClaimType` enum in `backend/app/schemas.py`
2. Add the field list to `REQUIRED_FIELDS` in `backend/app/claim_schema.py`
3. Update the claim type description in the extraction system prompt in `backend/app/prompts.py`

### Add a new mode

1. Add a value to `AssistantMode` in `backend/app/schemas.py`
2. Create a new agent (follow `advisor_agent.py` as a template)
3. Add a dispatch case in `backend/app/routers/chat.py`
4. Add a mode card in `frontend/src/components/ModeSelector.jsx`
