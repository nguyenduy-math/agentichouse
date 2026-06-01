# High-Level Design — Customer Service Assistant

## 1. System Overview

A Vietnamese-language customer service chatbot that routes each user message through a chain of AI agents. A dedicated MCP (Model Context Protocol) server exposes tools for data lookup and side-effect actions. The frontend shows both the chat and a live agent-activity sidebar.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (Vite + React)                  │
│                                                                  │
│   ┌──────────────────────────┐   ┌──────────────────────────┐  │
│   │       Chat Panel         │   │    Activity Sidebar       │  │
│   │  (messages + input bar)  │   │  (live agent/tool log)    │  │
│   └──────────────────────────┘   └──────────────────────────┘  │
│                         POST /api/chat                           │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FastAPI Backend  (port 8002)                    │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │                  OrchestratorAgent                       │   │
│   │   classify(message) ──► Gemini (JSON mode)              │   │
│   │        │                                                 │   │
│   │   ┌────▼────┐   ┌────────────┐   ┌──────────────────┐  │   │
│   │   │FAQAgent │   │ OrderAgent │   │ ComplaintAgent    │  │   │
│   │   │ Gemini  │   │SiliconFlow │   │     Gemini        │  │   │
│   │   └────┬────┘   └─────┬──────┘   └────────┬─────────┘  │   │
│   └────────┼──────────────┼───────────────────┼────────────┘   │
│            │   MCP tool calls (stdio)          │                 │
│            ▼              ▼                    ▼                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              MCPClientManager (stdio transport)          │   │
│   └───────────────────────┬─────────────────────────────────┘   │
└───────────────────────────┼─────────────────────────────────────┘
                            │ stdin/stdout (subprocess)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  MCP Server  (FastMCP)                           │
│                                                                  │
│   Query Tools                   Utility Tools                    │
│   ┌─────────────────────┐       ┌──────────────────────────┐   │
│   │ search_knowledge_base│       │ create_support_ticket     │   │
│   │ get_order_status     │       │ send_notification         │   │
│   │ get_customer_profile │       │ escalate_to_human         │   │
│   └─────────────────────┘       │ log_feedback              │   │
│           (mock data)            └──────────────────────────┘   │
│                                        (in-memory store)         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Descriptions

### 3.1 Frontend

| Component | Responsibility |
|---|---|
| `App.tsx` | State management (messages, activities, loading flag). Calls `POST /api/chat`. |
| `ChatWindow` | Renders message history; auto-scrolls to bottom. Shows typing animation while loading. |
| `MessageBubble` | Displays user/bot bubbles. Bot bubble shows an agent-type tag (FAQ / Order / Complaint). |
| `ActivitySidebar` | Renders the ordered activity log returned in the API response. Each entry shows the agent name, action, and tool detail. Animates in on arrival. |
| `InputBar` | Free-text textarea (Enter to send) plus four quick-prompt chips. |

### 3.2 FastAPI Backend

| Module | Responsibility |
|---|---|
| `main.py` | App factory, CORS, router registration, MCP subprocess lifecycle (start on startup, stop on shutdown). Serves `frontend/dist/` when built. |
| `config.py` | Reads `GEMINI_API_KEY`, `SILICONFLOW_*` from `.env` via Pydantic-settings. |
| `schemas.py` | `ChatRequest`, `ChatResponse`, `ActivityItem` Pydantic models. |
| `mcp_client.py` | `MCPClientManager` — wraps the MCP Python SDK's `stdio_client` + `ClientSession` in an `AsyncExitStack`. Exposes a single `call_tool(name, arguments)` coroutine. |
| `routers/chat.py` | `POST /chat` handler. Reads `mcp` from `app.state`, constructs `OrchestratorAgent`, awaits result. |

### 3.3 Agents

| Agent | LLM | Role |
|---|---|---|
| `OrchestratorAgent` | Gemini (JSON mode) | Classifies intent → routes to one specialist agent. Wraps errors into a friendly fallback reply. |
| `FAQAgent` | Gemini | Calls `search_knowledge_base`, builds context, generates a grounded answer. |
| `OrderAgent` | SiliconFlow (DeepSeek-V3) | Extracts order ID from message via regex, calls `get_order_status` + `get_customer_profile`, generates order status reply. |
| `ComplaintAgent` | Gemini | Calls `get_customer_profile`, then either `create_support_ticket` + `send_notification` (COMPLAINT) or `escalate_to_human` (ESCALATE). VIP customers get high-priority tickets. |

All prompts live in `agents/prompts.py` — no prompt text is scattered across agent files.

### 3.4 MCP Server

Runs as a **child process** of the backend, communicating over `stdin/stdout` (MCP stdio transport). The backend spawns it using `sys.executable` so the same virtual environment is used.

**Query tools** (read-only, return JSON strings):

| Tool | Input | Output |
|---|---|---|
| `search_knowledge_base` | `query: str` | Top-3 KB entries by keyword score |
| `get_order_status` | `order_id: str` | Order object or not-found message |
| `get_customer_profile` | `customer_id: str` | Profile + last 3 orders |

**Utility tools** (side-effect, write to in-memory stores):

| Tool | Input | Side effect |
|---|---|---|
| `create_support_ticket` | `customer_id, issue, priority` | Appends to `_tickets` dict |
| `send_notification` | `customer_id, message, channel` | Appends to `_notifications` list |
| `escalate_to_human` | `customer_id, reason, urgency` | Appends to `_escalations` list |
| `log_feedback` | `customer_id, rating, comment` | Appends to `_feedbacks` list |

---

## 4. Request Lifecycle

```
User types: "Đơn hàng ORD-2024-001 đang ở đâu?"
   │
   ▼
POST /api/chat  { message, customer_id: "CUST-001" }
   │
   ▼
OrchestratorAgent._classify()
   └─ Gemini (JSON): → { "category": "ORDER", "reason": "..." }
   │
   ▼
OrchestratorAgent routes → OrderAgent.handle()
   │
   ├─ MCP: get_order_status("ORD-2024-001")   → order JSON
   ├─ MCP: get_customer_profile("CUST-001")   → profile + recent orders
   └─ SiliconFlow: generate reply
   │
   ▼
ChatResponse {
  reply:      "Đơn hàng ORD-2024-001 đang được vận chuyển bởi Viettel Post...",
  agent_used: "order_agent",
  activities: [ {OrchestratorAgent, classify, ORDER}, {OrderAgent, tool, get_order_status}, ... ]
}
   │
   ▼
Frontend renders reply bubble + animates activity sidebar
```

---

## 5. Classification Routing

```
                    ┌──────────────────┐
  User message ───► │  OrchestratorAgent│
                    │  (Gemini JSON)    │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
           "FAQ"          "ORDER"     "COMPLAINT"
              │              │          "ESCALATE"
              ▼              ▼              ▼
          FAQAgent      OrderAgent   ComplaintAgent
                                    (escalate=True if ESCALATE)
```

---

## 6. LLM Provider Strategy

| Decision | Gemini | SiliconFlow (DeepSeek-V3) |
|---|---|---|
| Used for | Classification, FAQ, Complaint | Order queries |
| Why | Strong multilingual reasoning; native JSON mode for classification | Cost-effective for structured data retrieval tasks; demonstrates dual-provider setup |
| SDK | `google-genai` (`client.aio.models.generate_content`) | `openai` SDK with custom `base_url` |
| Config | `GEMINI_API_KEY`, `GEMINI_MODEL` | `SILICONFLOW_API_KEY`, `SILICONFLOW_BASE_URL`, `SILICONFLOW_MODEL` |

Both providers are configured in `config.py` and injected into agents at construction time, making it easy to swap or add providers.

---

## 7. Prompt Architecture

All prompt strings are centralised in `agents/prompts.py`:

```
prompts.py
├── ORCHESTRATOR_CLASSIFY   — JSON classification prompt with {message} placeholder
├── FAQ_SYSTEM              — Gemini system instruction for FAQ agent
├── FAQ_USER                — User turn template with {context} and {message} placeholders
├── ORDER_SYSTEM            — SiliconFlow system instruction for Order agent
├── COMPLAINT_SYSTEM        — Gemini system instruction for Complaint agent
└── COMPLAINT_USER          — User turn template with {context} and {message} placeholders
```

Agents only call `.format(...)` at the call site. To tune tone, language, or instructions, only `prompts.py` needs editing.

---

## 8. Extensibility

### Adding a new specialist agent

1. Create `app/agents/<name>_agent.py`.
2. Add its prompts to `prompts.py`.
3. Add a new classification label to `ORCHESTRATOR_CLASSIFY` in `prompts.py`.
4. Add a routing branch in `OrchestratorAgent.handle()`.

### Adding a new MCP server

1. Create `mcp_server_<name>/server.py` with a second `FastMCP` instance and its tools.
2. Instantiate a second `MCPClientManager` in `main.py` lifespan; store as `app.state.mcp_<name>`.
3. Pass it to whichever agents need it.

No changes to the existing MCP server or other agents required.

### Replacing mock data with a real database

The MCP tool functions in `query_tools.py` and `utility_tools.py` are the only files that touch data. Swap the in-memory dicts/lists for SQLAlchemy/asyncpg calls without touching agents, prompts, or the API layer.
