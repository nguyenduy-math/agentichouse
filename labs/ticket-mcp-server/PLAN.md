# Ticket MCP Server — Implementation Plan

> **Status**: Planning  
> **Target**: `labs/ticket-mcp-server/`  
> **Stack**: Python 3.11+, FastMCP (`mcp` SDK), Pydantic v2, aiosqlite  
> **Transport**: stdio (Claude Desktop + subprocess MCP client)

---

## 1. Overview

This is a standalone MCP server that exposes workplace ticket creation and management as tools callable by Claude. It covers six ticket types common to Vietnamese-language workplaces: nghỉ phép (leave), công tác (business trip), làm thêm giờ (overtime), yêu cầu thiết bị (equipment), đào tạo (training), and khác (other).

**Why standalone first.** Building it as an independent MCP server means it can be tested through Claude Desktop before any integration work, it has a single responsibility with a clean boundary, and it is deployable as a subprocess by any other service that speaks MCP JSON-RPC.

**Integration path to new-rag-2026.** After the server is stable, `new-rag-2026` will connect to it as an MCP subprocess client (the same pattern used by `insurance-assistant/mcp_client.py`). The `ProceduresAgent` inside new-rag-2026 will gain all ticket tools without any code duplication — it just connects to the subprocess and the MCP protocol exposes the tools automatically. See Section 7 for both options and the recommended approach.

---

## 2. Project Structure

```
ticket-mcp-server/
├── server.py                 # FastMCP entry point — registers all tools, runs stdio transport
├── tools/
│   ├── __init__.py
│   ├── ticket_tools.py       # create_ticket, get_ticket, list_tickets,
│   │                         #   update_ticket_status, add_comment
│   ├── leave_tools.py        # create_leave_request (type-specific validation)
│   ├── trip_tools.py         # create_trip_request
│   └── overtime_tools.py     # create_overtime_request
├── models/
│   ├── __init__.py
│   └── ticket.py             # Pydantic models + enums
├── storage/
│   ├── __init__.py
│   └── sqlite_store.py       # async SQLite via aiosqlite
├── config.py                 # DB path, defaults, env-var loading
├── requirements.txt
├── .env.example
└── README.md
```

### Module responsibilities

`server.py` — only wires FastMCP and imports tools. No business logic.

`tools/ticket_tools.py` — the five generic tools that work for any ticket type. Calls `sqlite_store` directly.

`tools/leave_tools.py`, `trip_tools.py`, `overtime_tools.py` — thin wrappers over `create_ticket` that enforce type-specific required fields, compute derived values (e.g., number of leave days), and return richer confirmation strings.

`models/ticket.py` — all Pydantic models and enums. Imported by tools and storage; nothing else imports tools.

`storage/sqlite_store.py` — all SQL. No Pydantic in this layer; accepts and returns plain dicts plus the models as needed.

`config.py` — reads `.env`, exposes a `Settings` dataclass with `db_path`, `default_priority`, etc.

---

## 3. Data Models (`models/ticket.py`)

```python
from enum import Enum
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, EmailStr


class TicketType(str, Enum):
    leave     = "leave"       # Nghỉ phép
    trip      = "trip"        # Công tác
    overtime  = "overtime"    # Làm thêm giờ
    equipment = "equipment"   # Yêu cầu thiết bị
    training  = "training"    # Đào tạo
    other     = "other"       # Khác


class LeaveType(str, Enum):
    annual    = "annual"      # Nghỉ phép năm
    sick      = "sick"        # Nghỉ ốm
    personal  = "personal"    # Nghỉ việc riêng
    unpaid    = "unpaid"      # Nghỉ không lương
    maternity = "maternity"   # Nghỉ thai sản (nữ)
    paternity = "paternity"   # Nghỉ thai sản (nam)


class TicketStatus(str, Enum):
    draft     = "draft"
    pending   = "pending"
    approved  = "approved"
    rejected  = "rejected"
    cancelled = "cancelled"
    completed = "completed"


class TicketPriority(str, Enum):
    low    = "low"
    normal = "normal"
    high   = "high"
    urgent = "urgent"


class Ticket(BaseModel):
    ticket_id:       str            = Field(..., description="TKT-YYYYMMDD-NNNN")
    ticket_type:     TicketType
    title:           str
    description:     str            = ""
    requester_name:  str            = Field(..., description="Tên người yêu cầu")
    requester_email: str            = Field(..., description="Email người yêu cầu")
    status:          TicketStatus   = TicketStatus.pending
    priority:        TicketPriority = TicketPriority.normal
    extra_fields:    dict[str, Any] = Field(default_factory=dict,
                                           description="Type-specific fields (JSON)")
    created_at:      datetime
    updated_at:      datetime


class TicketCreate(BaseModel):
    """Input model for generic create_ticket."""
    ticket_type:     TicketType
    title:           str
    description:     str            = ""
    requester_name:  str
    requester_email: str
    priority:        TicketPriority = TicketPriority.normal
    extra_fields:    dict[str, Any] = Field(default_factory=dict)


class TicketUpdate(BaseModel):
    """Input model for update_ticket_status."""
    ticket_id:     str
    new_status:    TicketStatus
    comment:       str  = ""
    approver_name: str  = ""
    approver_email: str = ""


class TicketHistory(BaseModel):
    id:           int
    ticket_id:    str
    action:       str          # "created" | "status_changed" | "comment_added"
    actor_name:   str
    actor_email:  str  = ""
    old_value:    str  = ""
    new_value:    str  = ""
    comment:      str  = ""
    timestamp:    datetime
```

### Status transition rules

| From       | Allowed transitions               |
|------------|-----------------------------------|
| `draft`    | → `pending`, `cancelled`          |
| `pending`  | → `approved`, `rejected`, `cancelled` |
| `approved` | → `completed`, `cancelled`        |
| `rejected` | → `pending` (resubmit), `cancelled` |
| `cancelled` | (terminal)                       |
| `completed` | (terminal)                       |

Enforce these in `update_ticket_status` — raise `ValueError` with a clear message if the transition is illegal.

---

## 4. SQLite Schema (`storage/sqlite_store.py`)

```sql
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id       TEXT PRIMARY KEY,        -- TKT-20260607-0001
    ticket_type     TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    requester_name  TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    priority        TEXT NOT NULL DEFAULT 'normal',
    extra_fields    TEXT NOT NULL DEFAULT '{}',  -- JSON blob
    created_at      TEXT NOT NULL,               -- ISO-8601 UTC
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       TEXT NOT NULL REFERENCES tickets(ticket_id),
    action          TEXT NOT NULL,   -- created | status_changed | comment_added
    actor_name      TEXT NOT NULL,
    actor_email     TEXT NOT NULL DEFAULT '',
    old_value       TEXT NOT NULL DEFAULT '',
    new_value       TEXT NOT NULL DEFAULT '',
    comment         TEXT NOT NULL DEFAULT '',
    timestamp       TEXT NOT NULL    -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_tickets_email  ON tickets(requester_email);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_type   ON tickets(ticket_type);
CREATE INDEX IF NOT EXISTS idx_history_ticket ON ticket_history(ticket_id);
```

### Ticket ID generation

```python
async def _next_ticket_id(conn, date_str: str) -> str:
    """
    date_str: 'YYYYMMDD'
    Returns: 'TKT-YYYYMMDD-NNNN' where NNNN is zero-padded count of tickets today + 1.
    Uses a SELECT COUNT within the same transaction to avoid races.
    """
    prefix = f"TKT-{date_str}-"
    async with conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE ticket_id LIKE ?",
        (prefix + "%",)
    ) as cur:
        row = await cur.fetchone()
    seq = (row[0] if row else 0) + 1
    return f"{prefix}{seq:04d}"
```

### `SqliteStore` class interface

```python
class SqliteStore:
    def __init__(self, db_path: str): ...

    async def init_db(self) -> None:
        """Create tables if not exists. Call once at server startup."""

    async def create(self, data: TicketCreate) -> Ticket:
        """Insert ticket + initial history row. Returns full Ticket."""

    async def get(self, ticket_id: str) -> Ticket | None:
        """Return Ticket or None if not found."""

    async def list_tickets(
        self,
        requester_email: str | None = None,
        status: str | None = None,
        ticket_type: str | None = None,
        limit: int = 20,
    ) -> list[Ticket]:
        """Filtered query. All filters are optional AND-combined."""

    async def update_status(
        self,
        ticket_id: str,
        new_status: str,
        comment: str,
        actor_name: str,
        actor_email: str = "",
    ) -> Ticket:
        """Update status, record history. Raises ValueError on bad transition."""

    async def add_comment(
        self,
        ticket_id: str,
        author_name: str,
        author_email: str,
        comment: str,
    ) -> None:
        """Append comment_added history row."""

    async def get_history(self, ticket_id: str) -> list[TicketHistory]:
        """Return all history rows for a ticket, oldest first."""
```

All methods open their own `aiosqlite.connect` context (or use a shared connection pool initialized at startup — either works; keep it simple with per-call connect for v1).

---

## 5. Tool Implementations

### 5.1 Generic ticket tools (`tools/ticket_tools.py`)

```python
from mcp.server.fastmcp import FastMCP
from storage.sqlite_store import SqliteStore
from models.ticket import TicketCreate, TicketType, TicketStatus, TicketPriority
import json

# store is injected from server.py via module-level variable
store: SqliteStore = None   # set by server.py before mcp.run()


@mcp.tool()
async def create_ticket(
    ticket_type: str,        # TicketType value
    title: str,
    description: str,
    requester_name: str,
    requester_email: str,
    priority: str = "normal",
    extra_fields: str = "{}",  # JSON string of type-specific fields
) -> str:
    """
    Tạo một ticket mới. Dùng công cụ này khi không có công cụ chuyên biệt cho loại yêu cầu.

    ticket_type must be one of: leave | trip | overtime | equipment | training | other
    priority must be one of: low | normal | high | urgent
    extra_fields: JSON string with any additional type-specific key/value pairs.

    Returns a confirmation string with ticket_id and status.
    Example: "✅ Ticket TKT-20260607-0001 đã được tạo\nLoại: other\nTrạng thái: Chờ phê duyệt"
    """
    data = TicketCreate(
        ticket_type=TicketType(ticket_type),
        title=title,
        description=description,
        requester_name=requester_name,
        requester_email=requester_email,
        priority=TicketPriority(priority),
        extra_fields=json.loads(extra_fields),
    )
    ticket = await store.create(data)
    return (
        f"✅ Ticket {ticket.ticket_id} đã được tạo\n"
        f"Loại: {ticket.ticket_type.value}\n"
        f"Trạng thái: Chờ phê duyệt"
    )


@mcp.tool()
async def get_ticket(ticket_id: str) -> str:
    """
    Lấy thông tin chi tiết của một ticket theo ID.

    ticket_id: ticket identifier in format TKT-YYYYMMDD-NNNN

    Returns full ticket details including status, fields, and history.
    Returns an error message if ticket_id does not exist.

    Example return:
    "📋 TKT-20260607-0001 — Nghỉ phép năm\nNgười yêu cầu: Nguyễn Văn A\n
    Trạng thái: pending\nƯu tiên: normal\nNgày tạo: 07/06/2026\n\nLịch sử:\n
    - 07/06/2026 10:00 — created by Nguyễn Văn A"
    """
    ticket = await store.get(ticket_id)
    if not ticket:
        return f"❌ Không tìm thấy ticket {ticket_id}"
    history = await store.get_history(ticket_id)
    lines = [
        f"📋 {ticket.ticket_id} — {ticket.title}",
        f"Loại: {ticket.ticket_type.value}",
        f"Người yêu cầu: {ticket.requester_name} <{ticket.requester_email}>",
        f"Trạng thái: {ticket.status.value}",
        f"Ưu tiên: {ticket.priority.value}",
        f"Tạo lúc: {ticket.created_at.strftime('%d/%m/%Y %H:%M')}",
        f"Cập nhật: {ticket.updated_at.strftime('%d/%m/%Y %H:%M')}",
    ]
    if ticket.extra_fields:
        lines.append("\nThông tin bổ sung:")
        for k, v in ticket.extra_fields.items():
            lines.append(f"  {k}: {v}")
    if history:
        lines.append("\nLịch sử:")
        for h in history:
            lines.append(
                f"  - {h.timestamp.strftime('%d/%m/%Y %H:%M')} "
                f"[{h.action}] bởi {h.actor_name}"
                + (f": {h.comment}" if h.comment else "")
            )
    return "\n".join(lines)


@mcp.tool()
async def list_tickets(
    requester_email: str = "",
    status: str = "",
    ticket_type: str = "",
    limit: int = 20,
) -> str:
    """
    Liệt kê danh sách ticket với bộ lọc tùy chọn.

    requester_email: filter by requester email (empty = all)
    status: filter by status — draft | pending | approved | rejected | cancelled | completed
    ticket_type: filter by type — leave | trip | overtime | equipment | training | other
    limit: max results to return (default 20, max 100)

    Returns a formatted list of matching tickets.
    Example: "📋 Danh sách ticket (3 kết quả)\n1. TKT-20260607-0001 — Nghỉ phép năm [pending]\n..."
    """
    tickets = await store.list_tickets(
        requester_email=requester_email or None,
        status=status or None,
        ticket_type=ticket_type or None,
        limit=min(limit, 100),
    )
    if not tickets:
        return "📭 Không có ticket nào phù hợp với bộ lọc."
    lines = [f"📋 Danh sách ticket ({len(tickets)} kết quả)"]
    for i, t in enumerate(tickets, 1):
        lines.append(
            f"{i}. {t.ticket_id} — {t.title} "
            f"[{t.status.value}] — {t.requester_name} "
            f"({t.created_at.strftime('%d/%m/%Y')})"
        )
    return "\n".join(lines)


@mcp.tool()
async def update_ticket_status(
    ticket_id: str,
    new_status: str,    # approved | rejected | cancelled | completed | pending
    comment: str = "",
    approver_name: str = "",
    approver_email: str = "",
) -> str:
    """
    Cập nhật trạng thái ticket (phê duyệt, từ chối, hủy, hoàn thành).

    ticket_id: ticket to update (TKT-YYYYMMDD-NNNN)
    new_status: target status — approved | rejected | cancelled | completed | pending
    comment: reason or note for the status change
    approver_name: name of the person making the change
    approver_email: email of the approver (optional)

    Returns a confirmation or an error if the transition is invalid.
    Example: "✅ TKT-20260607-0001 đã được cập nhật: pending → approved\nBởi: Trần Thị B"
    """
    try:
        ticket = await store.update_status(
            ticket_id=ticket_id,
            new_status=new_status,
            comment=comment,
            actor_name=approver_name or "System",
            actor_email=approver_email,
        )
        return (
            f"✅ {ticket.ticket_id} đã được cập nhật → {ticket.status.value}\n"
            f"Bởi: {approver_name or 'System'}"
            + (f"\nGhi chú: {comment}" if comment else "")
        )
    except ValueError as e:
        return f"❌ Lỗi: {e}"


@mcp.tool()
async def add_comment(
    ticket_id: str,
    author_name: str,
    comment: str,
    author_email: str = "",
) -> str:
    """
    Thêm ghi chú vào ticket mà không thay đổi trạng thái.

    ticket_id: target ticket (TKT-YYYYMMDD-NNNN)
    author_name: name of the person adding the comment
    comment: the comment text
    author_email: optional email of the author

    Returns confirmation or error message.
    Example: "💬 Đã thêm ghi chú vào TKT-20260607-0001"
    """
    ticket = await store.get(ticket_id)
    if not ticket:
        return f"❌ Không tìm thấy ticket {ticket_id}"
    await store.add_comment(ticket_id, author_name, author_email, comment)
    return f"💬 Đã thêm ghi chú vào {ticket_id}"
```

### 5.2 Lookup / utility tools (`tools/ticket_tools.py`, continued)

```python
@mcp.tool()
async def get_ticket_types() -> str:
    """
    Trả về danh sách tất cả loại ticket được hỗ trợ và các trường bắt buộc.

    Use this tool to understand what ticket types exist before creating one.
    Returns a formatted list of ticket types with their required fields.
    """
    return """📂 Các loại ticket được hỗ trợ:

1. leave (Nghỉ phép)
   Trường bắt buộc: leave_type, start_date, end_date, reason
   Loại nghỉ: annual | sick | personal | unpaid | maternity | paternity

2. trip (Công tác)
   Trường bắt buộc: destination, purpose, start_date, end_date
   Tùy chọn: estimated_budget_vnd, transport_mode

3. overtime (Làm thêm giờ)
   Trường bắt buộc: date, hours, reason
   Tùy chọn: project_code

4. equipment (Yêu cầu thiết bị)
   Trường bắt buộc: item_type, quantity, justification

5. training (Đào tạo)
   Trường bắt buộc: course_name, provider, start_date, end_date
   Tùy chọn: cost_vnd

6. other (Khác)
   Trường bắt buộc: description (mô tả chi tiết)"""


@mcp.tool()
async def get_ticket_statuses() -> str:
    """
    Trả về danh sách trạng thái hợp lệ và các chuyển đổi được phép.

    Use this before calling update_ticket_status to check valid transitions.
    """
    return """📊 Trạng thái ticket và chuyển đổi hợp lệ:

  draft      → pending, cancelled
  pending    → approved, rejected, cancelled
  approved   → completed, cancelled
  rejected   → pending (nộp lại), cancelled
  cancelled  → (kết thúc)
  completed  → (kết thúc)"""


@mcp.tool()
async def get_pending_approvals(approver_email: str = "") -> str:
    """
    Lấy danh sách ticket đang chờ phê duyệt.

    approver_email: if provided, returns all pending tickets (to be filtered by manager).
    Currently returns all tickets with status=pending since approver assignment
    is not yet modelled. Future version will filter by assigned approver.

    Returns a list of tickets needing action.
    """
    tickets = await store.list_tickets(status="pending", limit=50)
    if not tickets:
        return "✅ Không có ticket nào đang chờ phê duyệt."
    lines = [f"⏳ Ticket đang chờ phê duyệt ({len(tickets)} ticket):"]
    for i, t in enumerate(tickets, 1):
        lines.append(
            f"{i}. {t.ticket_id} — {t.title}\n"
            f"   Người yêu cầu: {t.requester_name} | "
            f"Loại: {t.ticket_type.value} | "
            f"Ngày: {t.created_at.strftime('%d/%m/%Y')}"
        )
    return "\n".join(lines)
```

### 5.3 Leave request tool (`tools/leave_tools.py`)

```python
@mcp.tool()
async def create_leave_request(
    requester_name: str,
    requester_email: str,
    leave_type: str,        # "annual" | "sick" | "personal" | "unpaid" | "maternity" | "paternity"
    start_date: str,        # YYYY-MM-DD
    end_date: str,          # YYYY-MM-DD
    reason: str,
    handover_person: str = "",
) -> str:
    """
    Tạo yêu cầu nghỉ phép. Sử dụng công cụ này khi nhân viên muốn xin nghỉ phép.

    leave_type: annual (phép năm) | sick (ốm) | personal (việc riêng) |
                unpaid (không lương) | maternity (thai sản nữ) | paternity (thai sản nam)
    start_date / end_date: YYYY-MM-DD format. end_date must be >= start_date.
    reason: reason for leave (required)
    handover_person: name of colleague handling duties during absence (optional)

    Returns confirmation with ticket_id, leave type, dates, number of days, and status.
    Example:
    "✅ Đã tạo yêu cầu nghỉ phép TKT-20260607-0001
    Loại: Nghỉ phép năm
    Từ: 10/06/2026 đến 12/06/2026 (3 ngày)
    Trạng thái: Chờ phê duyệt"
    """
```

**Validation rules for `create_leave_request`:**
- `leave_type` must be a valid `LeaveType` value → raise `ValueError` with list of valid options.
- Parse `start_date` and `end_date` as `datetime.date`. Raise `ValueError` if format is wrong.
- `end_date >= start_date` → raise `ValueError("end_date phải sau hoặc bằng start_date")`.
- `reason` must be non-empty → raise `ValueError("Vui lòng cung cấp lý do nghỉ phép")`.
- Compute `num_days = (end_date - start_date).days + 1`.
- Build `extra_fields = {"leave_type": leave_type, "start_date": start_date, "end_date": end_date, "num_days": num_days, "reason": reason, "handover_person": handover_person}`.
- Call `store.create(TicketCreate(ticket_type=TicketType.leave, title=f"Nghỉ phép — {leave_type_label} ({start_date} → {end_date})", ...))`.

**`leave_type_label` map:**

```python
LEAVE_LABELS = {
    "annual": "Nghỉ phép năm",
    "sick": "Nghỉ ốm",
    "personal": "Nghỉ việc riêng",
    "unpaid": "Nghỉ không lương",
    "maternity": "Nghỉ thai sản (nữ)",
    "paternity": "Nghỉ thai sản (nam)",
}
```

### 5.4 Business trip tool (`tools/trip_tools.py`)

```python
@mcp.tool()
async def create_trip_request(
    requester_name: str,
    requester_email: str,
    destination: str,           # e.g. "Hà Nội", "Singapore"
    purpose: str,
    start_date: str,            # YYYY-MM-DD
    end_date: str,              # YYYY-MM-DD
    estimated_budget_vnd: int = 0,
    transport_mode: str = "",   # "plane" | "train" | "car" | "other"
) -> str:
    """
    Tạo yêu cầu công tác. Sử dụng khi nhân viên cần đăng ký chuyến công tác.

    destination: city or country of travel (required)
    purpose: business justification (required)
    start_date / end_date: YYYY-MM-DD. end_date >= start_date.
    estimated_budget_vnd: estimated cost in VND (0 = not specified)
    transport_mode: plane | train | car | other (optional)

    Returns confirmation with ticket_id, destination, dates, duration, and status.
    Example:
    "✅ Đã tạo yêu cầu công tác TKT-20260607-0002
    Điểm đến: Hà Nội
    Từ: 15/06/2026 đến 17/06/2026 (3 ngày)
    Ngân sách dự kiến: 5,000,000 VND
    Trạng thái: Chờ phê duyệt"
    """
```

**Validation rules:**
- `destination` and `purpose` must be non-empty.
- Date parsing and `end_date >= start_date` same as leave.
- `estimated_budget_vnd >= 0`.
- `transport_mode` if provided must be in `["plane", "train", "car", "other", ""]`.

### 5.5 Overtime tool (`tools/overtime_tools.py`)

```python
@mcp.tool()
async def create_overtime_request(
    requester_name: str,
    requester_email: str,
    date: str,              # YYYY-MM-DD — the date overtime will be worked
    hours: float,           # e.g. 2.5 (must be > 0 and <= 12)
    reason: str,
    project_code: str = "",
) -> str:
    """
    Tạo yêu cầu làm thêm giờ. Sử dụng khi nhân viên cần đăng ký OT.

    date: YYYY-MM-DD date of overtime work (must not be in the past)
    hours: number of overtime hours (must be > 0 and <= 12)
    reason: business reason for overtime (required)
    project_code: optional project or cost-center code

    Returns confirmation with ticket_id, date, hours, and status.
    Example:
    "✅ Đã tạo yêu cầu làm thêm giờ TKT-20260607-0003
    Ngày: 08/06/2026 (Chủ nhật)
    Số giờ: 3.0 giờ
    Dự án: PRJ-2026-001
    Trạng thái: Chờ phê duyệt"
    """
```

**Validation rules:**
- `date` is a valid ISO date.
- `hours > 0` and `hours <= 12` → raise `ValueError("Số giờ phải từ 0 đến 12")`.
- `reason` non-empty.

---

## 6. `server.py` Design

```python
"""Ticket MCP Server — workplace ticket creation and management."""

import asyncio
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from config import settings                                              # noqa: E402
from storage.sqlite_store import SqliteStore                            # noqa: E402
import tools.ticket_tools as _tt                                        # noqa: E402
import tools.leave_tools as _lt                                         # noqa: E402
import tools.trip_tools as _trp                                         # noqa: E402
import tools.overtime_tools as _ot                                      # noqa: E402

mcp = FastMCP("ticket-server")

# Inject shared store into all tool modules before registering
store = SqliteStore(settings.db_path)
_tt.store = store
_lt.store = store
_trp.store = store
_ot.store = store


# --- Register tools ---

@mcp.tool()
async def create_ticket(*args, **kwargs): return await _tt.create_ticket(*args, **kwargs)

@mcp.tool()
async def get_ticket(*args, **kwargs): return await _tt.get_ticket(*args, **kwargs)

@mcp.tool()
async def list_tickets(*args, **kwargs): return await _tt.list_tickets(*args, **kwargs)

@mcp.tool()
async def update_ticket_status(*args, **kwargs): return await _tt.update_ticket_status(*args, **kwargs)

@mcp.tool()
async def add_comment(*args, **kwargs): return await _tt.add_comment(*args, **kwargs)

@mcp.tool()
async def get_ticket_types(*args, **kwargs): return await _tt.get_ticket_types(*args, **kwargs)

@mcp.tool()
async def get_ticket_statuses(*args, **kwargs): return await _tt.get_ticket_statuses(*args, **kwargs)

@mcp.tool()
async def get_pending_approvals(*args, **kwargs): return await _tt.get_pending_approvals(*args, **kwargs)

@mcp.tool()
async def create_leave_request(*args, **kwargs): return await _lt.create_leave_request(*args, **kwargs)

@mcp.tool()
async def create_trip_request(*args, **kwargs): return await _trp.create_trip_request(*args, **kwargs)

@mcp.tool()
async def create_overtime_request(*args, **kwargs): return await _ot.create_overtime_request(*args, **kwargs)


async def _startup():
    await store.init_db()


if __name__ == "__main__":
    asyncio.run(_startup())
    mcp.run()   # defaults to stdio transport
```

> **Note on tool registration**: The pattern above (thin wrapper lambdas) is verbose but explicit. An alternative is to define all `@mcp.tool()` decorators directly in the tool modules and import `mcp` from `server.py` — but that creates a circular import. The wrapper pattern avoids this cleanly. A cleaner alternative is to use `mcp.add_tool(fn)` programmatically after import; pick whichever reads more clearly.

---

## 7. Integration Path with new-rag-2026

### Option A — Direct Import (simpler, tighter coupling)

`new-rag-2026/agents/procedures_agent.py` imports `tools/ticket_tools.py` and the type-specific tools directly. The `ProceduresAgent` gains new tools as plain async functions. No subprocess, no JSON-RPC overhead.

**Pros**: Zero latency, no process management, easy to debug.  
**Cons**: The two codebases are coupled. Any change to the ticket server requires updating new-rag-2026. Cannot update/restart the ticket server independently.

### Option B — MCP Subprocess Client (recommended)

`new-rag-2026` launches `ticket-mcp-server/server.py` as a subprocess and communicates over stdio JSON-RPC — the same pattern as `insurance-assistant/mcp_client.py`. The `ProceduresAgent` uses an `McpClient` wrapper that calls `tools/call` on the subprocess.

**Pros**: Complete separation of concerns. Ticket server can be updated, versioned, and tested independently. Follows the MCP protocol exactly as designed. New tools added to the ticket server are available to new-rag-2026 immediately after restart.  
**Cons**: Slightly more latency (subprocess IPC), requires process lifecycle management.

**Recommendation: Option B.** The overhead is negligible for human-in-the-loop interactions, and the separation pays off as the server grows.

### JSON-RPC call format for `create_leave_request`

When new-rag-2026's MCP client calls `create_leave_request`, it sends:

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "create_leave_request",
    "arguments": {
      "requester_name": "Nguyễn Văn A",
      "requester_email": "a.nguyen@company.vn",
      "leave_type": "annual",
      "start_date": "2026-06-10",
      "end_date": "2026-06-12",
      "reason": "Du lịch gia đình",
      "handover_person": "Trần Thị B"
    }
  }
}
```

The server responds:

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "✅ Đã tạo yêu cầu nghỉ phép TKT-20260607-0001\nLoại: Nghỉ phép năm\nTừ: 10/06/2026 đến 12/06/2026 (3 ngày)\nTrạng thái: Chờ phê duyệt"
      }
    ]
  }
}
```

### Wiring in new-rag-2026

```python
# new-rag-2026/agents/procedures_agent.py  (sketch)
from mcp_client import McpClient   # existing pattern from insurance-assistant

ticket_client = McpClient(
    command=["python", "/path/to/ticket-mcp-server/server.py"]
)

async def handle_leave_request(user_message: str, user_email: str) -> str:
    # Claude extracts fields from user_message, then calls:
    return await ticket_client.call_tool("create_leave_request", {
        "requester_email": user_email,
        ...
    })
```

---

## 8. Claude Desktop Registration

Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "ticket-server": {
      "command": "python",
      "args": ["C:\\Users\\username\\path\\to\\ticket-mcp-server\\server.py"],
      "env": {
        "TICKET_DB_PATH": "C:\\Users\\username\\tickets.db"
      }
    }
  }
}
```

For macOS / Linux:

```json
{
  "mcpServers": {
    "ticket-server": {
      "command": "python3",
      "args": ["/home/username/labs/ticket-mcp-server/server.py"]
    }
  }
}
```

Restart Claude Desktop after saving. The tools appear automatically in Claude's tool list.

---

## 9. Example Conversation Flows

### Flow 1 — Creating a leave request

```
User:  Tôi muốn xin nghỉ phép năm từ ngày 10 đến 12 tháng 6. Email tôi là a.nguyen@company.vn.

Claude: [calls create_leave_request(
           requester_name="Nguyễn Văn A",
           requester_email="a.nguyen@company.vn",
           leave_type="annual",
           start_date="2026-06-10",
           end_date="2026-06-12",
           reason="Nghỉ phép năm",
         )]

Tool returns:
"✅ Đã tạo yêu cầu nghỉ phép TKT-20260607-0001
Loại: Nghỉ phép năm
Từ: 10/06/2026 đến 12/06/2026 (3 ngày)
Trạng thái: Chờ phê duyệt"

Claude: Đã tạo đơn xin nghỉ phép cho bạn với mã **TKT-20260607-0001**.
        Đơn nghỉ phép năm từ 10–12/06/2026 (3 ngày) hiện đang chờ phê duyệt.
```

### Flow 2 — Checking ticket status

```
User:  Đơn nghỉ phép của tôi đến đâu rồi? Email tôi là a.nguyen@company.vn.

Claude: [calls list_tickets(
           requester_email="a.nguyen@company.vn",
           ticket_type="leave",
           status="pending",
         )]

Tool returns:
"📋 Danh sách ticket (1 kết quả)
1. TKT-20260607-0001 — Nghỉ phép — Nghỉ phép năm (2026-06-10 → 2026-06-12) [pending] — Nguyễn Văn A (07/06/2026)"

Claude: Đơn nghỉ phép **TKT-20260607-0001** của bạn (10–12/06/2026) hiện đang ở trạng thái
        **chờ phê duyệt**. Bạn sẽ nhận thông báo khi đơn được xử lý.
```

### Flow 3 — Manager approving a ticket

```
User:  Tôi là Trần Thị B, quản lý. Duyệt đơn TKT-20260607-0001 cho nhân viên Nguyễn Văn A.

Claude: [calls update_ticket_status(
           ticket_id="TKT-20260607-0001",
           new_status="approved",
           comment="Đã xác nhận với nhân viên về người bàn giao",
           approver_name="Trần Thị B",
           approver_email="b.tran@company.vn",
         )]

Tool returns:
"✅ TKT-20260607-0001 đã được cập nhật → approved
Bởi: Trần Thị B
Ghi chú: Đã xác nhận với nhân viên về người bàn giao"

Claude: Đã phê duyệt đơn **TKT-20260607-0001** thành công.
        Đơn nghỉ phép của Nguyễn Văn A (10–12/06/2026) hiện trạng thái **Đã duyệt**.
```

---

## 10. `requirements.txt`

```
mcp>=1.0.0
pydantic>=2.0.0
aiosqlite>=0.20.0
python-dotenv>=1.0.0
```

No LLM dependencies — this server is pure tool logic. If email notification is added later, add `httpx` for outbound webhooks.

---

## 11. `.env.example`

```dotenv
# Path to SQLite database file. Defaults to ./tickets.db if not set.
TICKET_DB_PATH=./tickets.db

# Default priority for new tickets if not specified by the caller
TICKET_DEFAULT_PRIORITY=normal
```

---

## 12. Implementation Order

Work through the modules in this order to keep each layer testable before the next is built on top:

1. **`models/ticket.py`** — Define all enums and Pydantic models. Write unit tests for model validation (date fields, enum membership). Nothing else depends on this being done right, but everything breaks if it isn't.

2. **`config.py`** — Simple `Settings` dataclass reading from `.env`. Needed by `SqliteStore`.

3. **`storage/sqlite_store.py`** — Implement `SqliteStore` with all methods. Test independently with `pytest` + `aiosqlite` against an in-memory (`:memory:`) SQLite database. Cover: create, get, list with each filter, update_status (valid and invalid transitions), add_comment, get_history, sequential ticket ID generation.

4. **`tools/ticket_tools.py`** — Implement the five generic tools and three utility tools. At this point `store` is a module-level `None`; tests can inject a real `SqliteStore` pointing to `:memory:`. Do not use `@mcp.tool()` decorators yet — keep functions as plain `async def` and decorate only in `server.py` to keep testing simple.

5. **`tools/leave_tools.py`** — Implement `create_leave_request` with full validation. Unit test all validation branches (invalid leave_type, reversed dates, empty reason).

6. **`tools/trip_tools.py`** — Implement `create_trip_request` with validation. Same pattern.

7. **`tools/overtime_tools.py`** — Implement `create_overtime_request`. Validate hours range.

8. **`server.py`** — Wire FastMCP, inject store, register tools, call `store.init_db()` at startup, call `mcp.run()`. At this point the server is runnable: `python server.py` should start and accept stdin JSON-RPC.

9. **Manual test via Claude Desktop** — Register in `claude_desktop_config.json`, restart Claude Desktop, confirm all 11 tools appear, run through the three conversation flows from Section 9.

10. **`README.md`** — Installation instructions, Claude Desktop config example, tool reference table, example conversations.

11. **Integration into new-rag-2026** — Wire `McpClient` subprocess connection in `ProceduresAgent` per Option B in Section 7.

---

## 13. Design Notes and Decisions

**No approver assignment in v1.** The current data model does not track which manager is assigned to approve each ticket. `get_pending_approvals` returns all pending tickets. This is intentional — approver routing adds significant complexity (org chart, delegation, escalation) and is out of scope for v1. Add an `approver_email` column to `tickets` in v2 when the org structure is defined.

**`extra_fields` as JSON blob.** Type-specific fields (leave dates, trip destination, etc.) are stored as a single JSON column rather than separate tables. This keeps the schema simple and avoids a migration for every new ticket type. The trade-off is that you cannot SQL-filter on these fields directly. For v1 (small volume, filter by status/type/email is sufficient) this is fine.

**Async throughout.** All store methods are `async` and use `aiosqlite`. FastMCP tools are `async def`. This ensures the server never blocks the event loop on I/O.

**Return strings, not JSON.** MCP tool return values are consumed by Claude as text. Returning pre-formatted Vietnamese strings means Claude can relay them directly to users with minimal post-processing, which reduces hallucination of ticket details. If the server is later called by code (not Claude), JSON responses would be better — add a `format: "json" | "text"` parameter in v2.

**Ticket ID collisions.** The sequential ID uses `SELECT COUNT(*)` within the create transaction. Under concurrent writes (unlikely for a single-user desktop setup) this can produce duplicate IDs. For v1, add a `UNIQUE` constraint on `ticket_id` and retry on `IntegrityError`. For production, use a proper sequence or UUID.
