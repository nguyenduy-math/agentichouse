# Trợ lý Chính sách Doanh nghiệp

Hệ thống đa tác nhân RAG cho phép nhân viên đặt câu hỏi bằng tiếng Việt về mọi chính sách của công ty. **10 tác nhân chuyên gia** — mỗi tác nhân được trang bị công cụ truy xuất phù hợp nhất với loại tài liệu của mình — được điều phối bởi một OrchestratorAgent dùng Gemini để phân loại câu hỏi và tổng hợp kết quả.

```
Câu hỏi của nhân viên → OrchestratorAgent (phân loại lĩnh vực)
  ├── 1 lĩnh vực   → tác nhân chuyên gia → câu trả lời trực tiếp
  └── nhiều lĩnh vực → fan-out song song → tổng hợp câu trả lời
```

---

## Hai Công cụ Truy xuất

| Công cụ | Điểm mạnh | Dùng cho |
|---------|-----------|----------|
| **LightRAG** | Đồ thị tri thức + vector hybrid. Tìm mối quan hệ giữa các thực thể (vai trò, phòng ban, chính sách) qua nhiều tài liệu. | Nội quy LĐ, quy trình, sổ tay NV, đào tạo |
| **PageIndex** | Điều hướng cây phân cấp không cần vector. LLM lý luận qua mục lục tài liệu để trả lời với trích dẫn số trang chính xác. | Phúc lợi, quy tắc ứng xử, y tế, CNTT, tuân thủ, tài chính |

---

## 10 Tác nhân Chuyên gia

| Tác nhân | Domain Key | Công cụ | Thư mục | Phù hợp nhất cho |
|---------|-----------|---------|---------|-----------------|
| `HRPolicyAgent` | `HR_POLICY` | LightRAG (hybrid) | `hr_policies/` | Hợp đồng LĐ, nghỉ phép, giờ làm, đánh giá hiệu suất |
| `BenefitsAgent` | `BENEFITS` | PageIndex | `benefits/` | Lương thưởng, bảo hiểm, hưu trí, phụ cấp — cần số trang chính xác |
| `ConductAgent` | `CONDUCT` | PageIndex | `conduct/` | Quy tắc ứng xử, trang phục, kỷ luật — cần trích dẫn điều khoản |
| `ProceduresAgent` | `PROCEDURES` | LightRAG (hybrid) | `procedures/` | Quy trình từng bước, chuỗi phê duyệt, onboarding |
| `HandbookAgent` | `HANDBOOK` | LightRAG (global) | `handbooks/` | Văn hóa công ty, sứ mệnh, thông tin chung nhân viên mới |
| `MedicalAgent` | `MEDICAL` | PageIndex | `medical/` | Bảo hiểm y tế, danh sách bệnh viện, mức hoàn trả |
| `ITSecurityAgent` | `IT_SECURITY` | PageIndex | `it_security/` | Sử dụng thiết bị, mật khẩu, bảo mật dữ liệu, quyền truy cập |
| `ComplianceAgent` | `COMPLIANCE` | PageIndex | `compliance/` | Luật lao động, bảo vệ dữ liệu (PDPA), phòng chống tham nhũng |
| `FinanceAgent` | `FINANCE` | PageIndex | `finance/` | Hạn mức chi phí, hoàn ứng, phê duyệt ngân sách, công tác phí |
| `TrainingAgent` | `TRAINING` | LightRAG (hybrid) | `training/` | Lộ trình sự nghiệp, chương trình đào tạo, học bổng, chứng chỉ |

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
│   │   │   ├── hr_policy_agent.py     # LightRAG — Nội quy lao động
│   │   │   ├── benefits_agent.py      # PageIndex — Phúc lợi & đãi ngộ
│   │   │   ├── conduct_agent.py       # PageIndex — Quy tắc ứng xử
│   │   │   ├── procedures_agent.py    # LightRAG — Quy trình & thủ tục
│   │   │   ├── handbook_agent.py      # LightRAG — Sổ tay nhân viên
│   │   │   ├── medical_agent.py       # PageIndex — Chính sách y tế
│   │   │   ├── it_security_agent.py   # PageIndex — CNTT & Bảo mật
│   │   │   ├── compliance_agent.py    # PageIndex — Tuân thủ & Pháp lý
│   │   │   ├── finance_agent.py       # PageIndex — Chính sách tài chính
│   │   │   └── training_agent.py      # LightRAG — Đào tạo & Phát triển
│   │   ├── services/
│   │   │   ├── lightrag_service.py    # LightRAGService class (per-domain instance)
│   │   │   └── pageindex_service.py   # PageIndexService (tree index + Gemini navigation)
│   │   └── routers/
│   │       ├── health.py              # GET /health (per-agent status)
│   │       ├── ingest.py              # POST /ingest, /ingest/upload
│   │       ├── chat.py                # POST /chat
│   │       └── admin.py               # GET /admin/stats, /admin/agents, POST /admin/reindex
│   ├── data/documents/
│   │   ├── hr_policies/               # Nội quy lao động, hợp đồng, chính sách nghỉ phép
│   │   ├── benefits/                  # Phúc lợi, lương thưởng, hưu trí, phụ cấp
│   │   ├── conduct/                   # Quy tắc ứng xử, đạo đức, kỷ luật
│   │   ├── procedures/                # SOP, quy trình onboarding, hướng dẫn đề xuất
│   │   ├── handbooks/                 # Sổ tay nhân viên, văn hóa công ty
│   │   ├── medical/                   # Chính sách y tế, bảo hiểm sức khỏe, danh sách bệnh viện
│   │   ├── it_security/               # Chính sách CNTT, bảo mật thông tin, quy định thiết bị
│   │   ├── compliance/                # Luật lao động, PDPA, phòng chống tham nhũng
│   │   ├── finance/                   # Chính sách tài chính, hạn mức chi phí, hoàn ứng
│   │   └── training/                  # Chương trình đào tạo, lộ trình sự nghiệp, học bổng
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

# PageIndex is not on PyPI — install from GitHub:
pip install git+https://github.com/VectifyAI/PageIndex.git
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in at minimum:

```ini
GEMINI_API_KEY=your-key-here
NEO4J_PASSWORD=please-change-me   # must match docker-compose.yml
```

### 4. Start the backend

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On startup, all five domain agents initialize. LightRAG agents connect to Neo4j and set up their storage directories. PageIndex agents load their document registries.

### 5. Start the frontend (dev)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

---

## Usage

### Tải lên tài liệu

Dùng thanh tải lên ở đầu cửa sổ chat. Chọn lĩnh vực tương ứng với tài liệu rồi nhấn **Tải lên tài liệu**.

| Lĩnh vực | Tài liệu nên tải lên |
|----------|---------------------|
| Nội quy lao động | Chính sách nghỉ phép, mẫu hợp đồng lao động, quy định giờ làm việc |
| Phúc lợi & đãi ngộ | Thang bảng lương, kế hoạch bảo hiểm sức khỏe, quy chế thưởng |
| Quy tắc ứng xử | Quy tắc ứng xử, chính sách chống quấy rối, quy định trang phục |
| Quy trình & thủ tục | Quy trình onboarding, hướng dẫn hoàn ứng, workflow phê duyệt |
| Sổ tay nhân viên | Sổ tay nhân viên, giá trị công ty, hướng dẫn văn phòng |
| Chính sách y tế | Hợp đồng bảo hiểm sức khỏe, danh sách bệnh viện, quy trình khám chữa bệnh |
| CNTT & Bảo mật | Chính sách bảo mật CNTT, quy định sử dụng thiết bị, hướng dẫn mật khẩu |
| Tuân thủ & Pháp lý | Nội quy về luật lao động, chính sách bảo vệ dữ liệu (PDPA), quy chế phòng chống tham nhũng |
| Chính sách tài chính | Quy chế tài chính, hạn mức chi phí, quy trình hoàn ứng công tác phí |
| Đào tạo & Phát triển | Chương trình đào tạo, lộ trình sự nghiệp, quy chế học bổng và chứng chỉ |

Hoặc nạp toàn bộ thư mục qua API:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"folder": null}'
```

### Đặt câu hỏi

Gõ bất kỳ câu hỏi nào bằng tiếng Việt. OrchestratorAgent tự động phân loại và định tuyến đến đúng tác nhân chuyên gia.

**Ví dụ một lĩnh vực:**

| Câu hỏi | Tác nhân | Công cụ |
|---------|---------|---------|
| "Tôi được nghỉ phép năm bao nhiêu ngày?" | BENEFITS | PageIndex → trích dẫn trang |
| "Thứ Sáu casual có được phép không với nhà thầu?" | CONDUCT | PageIndex → trích dẫn trang |
| "Chính sách nghỉ phép liên quan đến làm việc từ xa như thế nào?" | HR_POLICY | LightRAG → đồ thị thực thể |
| "Các bước để nộp đề xuất hoàn ứng là gì?" | PROCEDURES | LightRAG → graph traversal |
| "Gói bảo hiểm sức khỏe của tôi bao gồm những bệnh viện nào?" | MEDICAL | PageIndex → trích dẫn trang |
| "Tôi có được cài phần mềm cá nhân trên máy tính công ty không?" | IT_SECURITY | PageIndex → trích dẫn điều khoản |
| "Hạn mức chi phí công tác nội địa là bao nhiêu?" | FINANCE | PageIndex → trích dẫn số tiền |
| "Điều kiện để được cử đi học chứng chỉ chuyên môn là gì?" | TRAINING | LightRAG → quan hệ thực thể |

**Ví dụ đa lĩnh vực:**

> "Nhân viên bán thời gian có được hưởng bảo hiểm y tế không, và quyền nghỉ ốm của họ là bao nhiêu ngày?"

→ Tham vấn `HR_POLICY` + `BENEFITS` + `MEDICAL` song song → câu trả lời tổng hợp với trích dẫn trang từ tài liệu phúc lợi và ngữ cảnh đồ thị từ nội quy lao động.

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
    "CONDUCT":     { "ready": false, "engine_type": "pageindex",  "indexed_docs": 0 },
    "PROCEDURES":  { "ready": true,  "engine_type": "lightrag",   "indexed_docs": 2 },
    "HANDBOOK":    { "ready": false, "engine_type": "lightrag",   "indexed_docs": 0 }
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

Valid `doc_type` values: `hr_policies`, `benefits`, `conduct`, `procedures`, `handbooks`.

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
  "entities": [],
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
    │   ├── hr_policy/      ← LightRAG vector + KV store (HR_POLICY agent)
    │   ├── procedures/     ← LightRAG vector + KV store (PROCEDURES agent)
    │   └── handbook/       ← LightRAG vector + KV store (HANDBOOK agent)
    └── pageindex/
        ├── benefits/       ← JSON trees + registry.json (BENEFITS agent)
        └── conduct/        ← JSON trees + registry.json (CONDUCT agent)
```

Neo4j stores the entity/relation graphs for all LightRAG agents (shared instance, isolated by `working_dir`).

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Google Gemini 2.5 Flash |
| Embeddings | gemini-embedding-001 (1536d) |
| Graph RAG | [LightRAG](https://github.com/HKUDS/LightRAG) |
| Vectorless RAG | [PageIndex](https://github.com/VectifyAI/PageIndex) |
| Graph DB | Neo4j 5 |
| Backend | FastAPI + Uvicorn |
| Config | Pydantic-settings |
| Frontend | React 18 + Vite |
