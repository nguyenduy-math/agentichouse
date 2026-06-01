# Customer Service Assistant

AI-powered customer service chatbot with a multi-agent backend, an MCP tool server, and a React frontend. Built for the Vietnamese market — all LLM prompts and responses are in Vietnamese.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.11+) |
| Agents / Orchestration | Custom async agents |
| LLM — classification & FAQ | Google Gemini (`gemini-2.5-flash`) via `google-genai` |
| LLM — order queries | SiliconFlow (`deepseek-ai/DeepSeek-V3`) via OpenAI-compatible SDK |
| Tool server | FastMCP (Model Context Protocol) |
| Frontend | React 18 + TypeScript + Vite |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A **Gemini API key** — [aistudio.google.com](https://aistudio.google.com)
- A **SiliconFlow API key** — [siliconflow.cn](https://siliconflow.cn)

---

## Quick Start

### 1. Backend

```bash
cd backend

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env   # then fill in your API keys
```

`.env` minimal config:

```env
GEMINI_API_KEY=your-gemini-key
SILICONFLOW_API_KEY=your-siliconflow-key
```

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

The MCP server is spawned automatically as a subprocess on startup — no separate step needed.

### 2. Frontend (development)

```bash
cd frontend
npm install
npm run dev          # → http://localhost:5173
```

### 3. Frontend (production build)

```bash
cd frontend && npm run build
# FastAPI will serve frontend/dist/ automatically — no separate process needed
uvicorn app.main:app --host 0.0.0.0 --port 8002
```

---

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Send a message, receive reply + agent activity log |
| `GET` | `/api/health` | Health check |

**Request body:**
```json
{
  "message": "Đơn hàng ORD-2024-001 đang ở đâu?",
  "customer_id": "CUST-001"
}
```

**Response:**
```json
{
  "reply": "Đơn hàng ORD-2024-001 của bạn đang được vận chuyển bởi Viettel Post...",
  "agent_used": "order_agent",
  "activities": [
    { "agent": "OrchestratorAgent", "action": "Phân loại câu hỏi", "detail": "ORDER — câu hỏi về đơn hàng cụ thể" },
    { "agent": "OrderAgent", "action": "Gọi công cụ", "detail": "get_order_status(ORD-2024-001)" },
    { "agent": "OrderAgent", "action": "Gọi công cụ", "detail": "get_customer_profile(CUST-001)" },
    { "agent": "OrderAgent", "action": "Tạo phản hồi", "detail": "SiliconFlow (deepseek-ai/DeepSeek-V3)" }
  ]
}
```

---

## Mock Data

The MCP server ships with in-memory mock data for development.

### Customers

| ID | Name | Tier |
|---|---|---|
| `CUST-001` | Nguyễn Văn An | Thành viên Vàng |
| `CUST-002` | Trần Thị Bình | Thành viên Bạc |
| `GUEST` | Khách vãng lai | Khách |

### Orders

| ID | Customer | Status |
|---|---|---|
| `ORD-2024-001` | CUST-001 | Đang vận chuyển |
| `ORD-2024-002` | CUST-001 | Đã giao hàng |
| `ORD-2024-003` | CUST-002 | Đang xử lý |
| `ORD-2024-004` | CUST-002 | Đã hủy |

### Quick prompts to try

- `Đơn hàng ORD-2024-001 đang ở đâu?` → OrderAgent
- `Chính sách đổi trả hàng?` → FAQAgent
- `Phí vận chuyển tính như thế nào?` → FAQAgent
- `Sản phẩm tôi nhận bị lỗi` → ComplaintAgent
- `Tôi muốn gặp nhân viên thật` → ComplaintAgent (escalate)

---

## Project Structure

```
customer-service-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app + MCP lifespan
│   │   ├── config.py                # Pydantic-settings (.env)
│   │   ├── schemas.py               # Request / response models
│   │   ├── mcp_client.py            # MCPClientManager (stdio transport)
│   │   ├── routers/
│   │   │   └── chat.py              # POST /chat, GET /health
│   │   └── agents/
│   │       ├── prompts.py           # All LLM prompts (single source of truth)
│   │       ├── orchestrator.py      # Routes messages to specialized agents
│   │       ├── faq_agent.py         # General Q&A (Gemini)
│   │       ├── order_agent.py       # Order lookups (SiliconFlow)
│   │       └── complaint_agent.py   # Complaints & escalations (Gemini)
│   ├── mcp_server/
│   │   ├── server.py                # FastMCP entry point
│   │   └── tools/
│   │       ├── query_tools.py       # search_knowledge_base, get_order_status, get_customer_profile
│   │       └── utility_tools.py     # create_support_ticket, send_notification, escalate_to_human, log_feedback
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── src/
        ├── App.tsx                  # Two-panel layout
        ├── App.css
        ├── types.ts
        └── components/
            ├── ChatWindow.tsx       # Auto-scrolling message list
            ├── MessageBubble.tsx    # User / bot bubbles
            ├── ActivitySidebar.tsx  # Live agent activity log
            └── InputBar.tsx        # Textarea + quick-prompt chips
```

---

## Adding a New MCP Server

The architecture is designed to be extended with additional MCP servers (e.g. a CRM server, a payments server):

1. Create `mcp_server_<name>/server.py` with a new `FastMCP` instance and its tools.
2. Instantiate a second `MCPClientManager` in `app/main.py` lifespan and store it in `app.state`.
3. Pass it to whichever agents need it.

No changes to the existing MCP server or agents are required.
