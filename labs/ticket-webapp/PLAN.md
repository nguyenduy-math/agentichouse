# Ticket Webapp — Implementation Plan

> **Status**: Planning document only. No code has been written yet.
> **Language**: Vietnamese UI, English code/docs.

---

## 1. Overview

### What the app does

A full-stack ticket management portal that lets employees, managers, and admins work with the same SQLite database used by the `ticket-mcp-server`. The web app shares the database file directly — tickets submitted via Claude Desktop appear in the web UI, and vice versa.

### Integration pattern: direct import (shared library)

The FastAPI backend adds `ticket-mcp-server/` to `sys.path` and imports `SqliteStore`, all Pydantic models, and the `STATUS_TRANSITIONS` dict directly. No subprocess, no MCP JSON-RPC overhead. The MCP `server.py` continues to work for Claude Desktop usage unchanged.

```
ticket-mcp-server/         ← shared library + Claude Desktop MCP server
  data/tickets.db          ← single source of truth (shared)

ticket-webapp/
  backend/                 ← FastAPI; imports ticket-mcp-server directly
  frontend/                ← React/TypeScript SPA
```

### User personas

| Persona | What they can do |
|---------|-----------------|
| **Employee** | Submit new tickets, view own tickets, cancel own draft/pending tickets, add comments |
| **Manager** | Everything employees can + approve or reject any pending ticket |
| **Admin** | Everything + see all tickets (any requester), filter/search across all fields, export CSV |

No authentication in v1. Users self-identify via a profile form (name + email) stored in `localStorage`. Role is selected the same way — honour-system for v1.

---

## 2. Project structure

```
ticket-webapp/
├── PLAN.md                          ← this file
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app + lifespan startup
│   │   ├── config.py                # Settings (DB path, MCP path, CORS)
│   │   ├── schemas.py               # REST-layer Pydantic models
│   │   ├── services/
│   │   │   └── ticket_service.py    # Thin async wrapper around SqliteStore
│   │   └── routers/
│   │       ├── tickets.py           # CRUD endpoints
│   │       ├── approvals.py         # Approval workflow endpoints
│   │       └── health.py
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/
        │   └── ticketApi.ts          # All fetch calls to /api/v1/...
        ├── store/
        │   └── index.ts              # Zustand: userProfile, activeFilters, role
        ├── hooks/
        │   └── useTickets.ts         # SWR hook for ticket list with polling
        ├── components/
        │   ├── layout/
        │   │   ├── AppShell.tsx
        │   │   └── Header.tsx
        │   ├── tickets/
        │   │   ├── TicketList.tsx    # Filterable table/card list
        │   │   ├── TicketCard.tsx    # Single ticket summary row
        │   │   ├── TicketDetail.tsx  # Full ticket + history timeline
        │   │   └── TicketBadge.tsx   # Colored status + type badges
        │   ├── forms/
        │   │   ├── NewTicketModal.tsx   # Type selector + dynamic form
        │   │   ├── LeaveForm.tsx
        │   │   ├── TripForm.tsx
        │   │   ├── OvertimeForm.tsx
        │   │   ├── EquipmentForm.tsx
        │   │   ├── TrainingForm.tsx
        │   │   └── GenericForm.tsx
        │   └── approvals/
        │       └── ApprovalPanel.tsx    # Pending tickets with inline actions
        └── pages/
            ├── MyTicketsPage.tsx        # Employee view
            ├── AllTicketsPage.tsx       # Admin view
            └── ApprovalsPage.tsx        # Manager view
```

---

## 3. Backend REST API design

All routes are prefixed `/api/v1`.

### Tickets

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tickets` | Create any ticket type (generic) |
| `POST` | `/tickets/leave` | Create leave request (type-specific, validates leave logic) |
| `POST` | `/tickets/trip` | Create trip request |
| `POST` | `/tickets/overtime` | Create overtime request |
| `POST` | `/tickets/equipment` | Create equipment request |
| `POST` | `/tickets/training` | Create training request |
| `GET`  | `/tickets` | List tickets with optional filters |
| `GET`  | `/tickets/{ticket_id}` | Full ticket details + history |
| `PATCH` | `/tickets/{ticket_id}/status` | Change status (approve / reject / cancel / complete) |
| `POST` | `/tickets/{ticket_id}/comments` | Add comment without changing status |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tickets/stats` | Counts by status and by type |
| `GET` | `/tickets/export` | CSV download of all (or filtered) tickets |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{"status": "ok", "db": "<path>"}` |

### Query parameters for `GET /tickets`

| Param | Type | Description |
|-------|------|-------------|
| `requester_email` | string | Filter by requester |
| `status` | string | One of the `TicketStatus` values |
| `ticket_type` | string | One of the `TicketType` values |
| `limit` | int (default 50, max 200) | Page size |
| `offset` | int (default 0) | Page offset — implemented in service layer via Python slice since `SqliteStore.list_tickets` fetches `limit + offset` rows and slices |

> **Note on offset**: `SqliteStore.list_tickets` accepts only `limit`, not `offset`. The service layer works around this by fetching `limit + offset` rows then slicing `[offset:]`. For v2, add native `OFFSET` support to `SqliteStore`.

---

## 4. Request/response schemas (`schemas.py`)

These are REST-layer models, deliberately separate from the MCP server's own models. This prevents tight coupling if the MCP models evolve.

```python
# schemas.py
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, EmailStr


# ── Enums (re-exported as string literals for OpenAPI clarity) ──────────────

class TicketTypeEnum(str, Enum):
    leave = "leave"; trip = "trip"; overtime = "overtime"
    equipment = "equipment"; training = "training"; other = "other"

class StatusEnum(str, Enum):
    draft = "draft"; pending = "pending"; approved = "approved"
    rejected = "rejected"; cancelled = "cancelled"; completed = "completed"

class PriorityEnum(str, Enum):
    low = "low"; normal = "normal"; high = "high"; urgent = "urgent"

class LeaveTypeEnum(str, Enum):
    annual = "annual"; sick = "sick"; personal = "personal"
    unpaid = "unpaid"; maternity = "maternity"; paternity = "paternity"

class TransportModeEnum(str, Enum):
    plane = "plane"; train = "train"; car = "car"; other = "other"


# ── Creation requests ────────────────────────────────────────────────────────

class RequesterBase(BaseModel):
    requester_name:  str = Field(..., min_length=1)
    requester_email: EmailStr
    priority:        PriorityEnum = PriorityEnum.normal

class CreateLeaveRequest(RequesterBase):
    leave_type:      LeaveTypeEnum
    start_date:      str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date:        str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    reason:          str = Field(..., min_length=1)
    handover_person: str = ""

class CreateTripRequest(RequesterBase):
    destination:          str = Field(..., min_length=1)
    purpose:              str = Field(..., min_length=1)
    start_date:           str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date:             str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    estimated_budget_vnd: int = Field(0, ge=0)
    transport_mode:       TransportModeEnum | None = None

class CreateOvertimeRequest(RequesterBase):
    date:         str   = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    hours:        float = Field(..., gt=0, le=12)
    reason:       str   = Field(..., min_length=1)
    project_code: str   = ""

class CreateEquipmentRequest(RequesterBase):
    item_type:     str = Field(..., min_length=1)
    quantity:      int = Field(..., ge=1)
    justification: str = Field(..., min_length=1)
    description:   str = ""

class CreateTrainingRequest(RequesterBase):
    course_name:  str = Field(..., min_length=1)
    provider:     str = Field(..., min_length=1)
    start_date:   str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date:     str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    cost_vnd:     int = Field(0, ge=0)
    description:  str = ""

class CreateGenericTicket(RequesterBase):
    ticket_type:  TicketTypeEnum
    title:        str = Field(..., min_length=1)
    description:  str = ""
    extra_fields: dict[str, Any] = Field(default_factory=dict)


# ── Status update / comment ──────────────────────────────────────────────────

class StatusUpdateRequest(BaseModel):
    new_status:     StatusEnum
    comment:        str = ""
    approver_name:  str = Field(..., min_length=1)
    approver_email: EmailStr | None = None

class CommentRequest(BaseModel):
    author_name:  str = Field(..., min_length=1)
    author_email: EmailStr | None = None
    comment:      str = Field(..., min_length=1)


# ── Responses ────────────────────────────────────────────────────────────────

class HistoryEntry(BaseModel):
    id:          int
    action:      str          # "created" | "status_changed" | "comment_added"
    actor_name:  str
    actor_email: str
    old_value:   str
    new_value:   str
    comment:     str
    timestamp:   datetime

class TicketListItem(BaseModel):
    ticket_id:       str
    ticket_type:     TicketTypeEnum
    title:           str
    requester_name:  str
    requester_email: str
    status:          StatusEnum
    priority:        PriorityEnum
    created_at:      datetime
    updated_at:      datetime

class TicketResponse(TicketListItem):
    description:  str
    extra_fields: dict[str, Any]   # leave/trip/overtime fields live here
    history:      list[HistoryEntry] = []

class TicketListResponse(BaseModel):
    total:   int                   # count of rows matching filters (before limit/offset)
    items:   list[TicketListItem]
    limit:   int
    offset:  int

class TicketStats(BaseModel):
    by_status: dict[str, int]      # {"pending": 5, "approved": 12, ...}
    by_type:   dict[str, int]      # {"leave": 8, "trip": 3, ...}
    total:     int
```

---

## 5. Backend service layer (`app/services/ticket_service.py`)

A thin async class that bridges the REST layer to `SqliteStore`. All business-logic validation that already exists in the MCP tools is replicated here (date checks, enum checks) so the REST endpoints don't need to know MCP internals.

```python
# app/services/ticket_service.py
import sys
from pathlib import Path

# Inject ticket-mcp-server onto sys.path so its modules are importable.
# MCP_SERVER_PATH is resolved at startup from config (absolute path).
_MCP_PATH = str(Path(__file__).parent.parent.parent.parent / "ticket-mcp-server")
if _MCP_PATH not in sys.path:
    sys.path.insert(0, _MCP_PATH)

from storage.sqlite_store import SqliteStore          # noqa: E402
from models.ticket import (                           # noqa: E402
    Ticket, TicketCreate, TicketType, TicketStatus,
    TicketPriority, LeaveType, STATUS_TRANSITIONS,
)

from app.config import settings
from app.schemas import (
    CreateLeaveRequest, CreateTripRequest, CreateOvertimeRequest,
    CreateEquipmentRequest, CreateTrainingRequest, CreateGenericTicket,
    StatusUpdateRequest, CommentRequest,
    TicketResponse, TicketListItem, TicketListResponse,
    HistoryEntry, TicketStats,
)


class TicketService:
    def __init__(self) -> None:
        self._store = SqliteStore(settings.ticket_db_path)

    async def init(self) -> None:
        await self._store.init_db()

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _ticket_to_list_item(t: Ticket) -> TicketListItem:
        return TicketListItem(**t.model_dump())

    @staticmethod
    def _ticket_to_response(t: Ticket, history) -> TicketResponse:
        return TicketResponse(
            **t.model_dump(),
            history=[HistoryEntry(**h.model_dump()) for h in history],
        )

    # ── create variants ───────────────────────────────────────────────────────

    async def create_leave(self, req: CreateLeaveRequest) -> TicketResponse:
        from datetime import date
        sd, ed = date.fromisoformat(req.start_date), date.fromisoformat(req.end_date)
        if ed < sd:
            raise ValueError("end_date phải sau hoặc bằng start_date")
        lt = LeaveType(req.leave_type.value)
        num_days = (ed - sd).days + 1
        extra = {
            "leave_type": lt.value,
            "leave_label": lt.value,   # frontend maps to Vietnamese label
            "start_date": req.start_date,
            "end_date": req.end_date,
            "num_days": num_days,
            "reason": req.reason,
            "handover_person": req.handover_person,
        }
        data = TicketCreate(
            ticket_type=TicketType.leave,
            title=f"Nghỉ phép — {lt.value} ({req.start_date} → {req.end_date})",
            description=req.reason,
            requester_name=req.requester_name,
            requester_email=req.requester_email,
            priority=TicketPriority(req.priority.value),
            extra_fields=extra,
        )
        ticket = await self._store.create(data)
        history = await self._store.get_history(ticket.ticket_id)
        return self._ticket_to_response(ticket, history)

    async def create_trip(self, req: CreateTripRequest) -> TicketResponse: ...
    async def create_overtime(self, req: CreateOvertimeRequest) -> TicketResponse: ...
    async def create_equipment(self, req: CreateEquipmentRequest) -> TicketResponse: ...
    async def create_training(self, req: CreateTrainingRequest) -> TicketResponse: ...
    async def create_generic(self, req: CreateGenericTicket) -> TicketResponse: ...

    # ── read ──────────────────────────────────────────────────────────────────

    async def get_ticket(self, ticket_id: str) -> TicketResponse:
        ticket = await self._store.get(ticket_id)
        if not ticket:
            raise KeyError(ticket_id)
        history = await self._store.get_history(ticket_id)
        return self._ticket_to_response(ticket, history)

    async def list_tickets(
        self,
        requester_email: str | None,
        status: str | None,
        ticket_type: str | None,
        limit: int,
        offset: int,
    ) -> TicketListResponse:
        # Workaround: fetch limit+offset rows, then slice.
        rows = await self._store.list_tickets(
            requester_email=requester_email,
            status=status,
            ticket_type=ticket_type,
            limit=limit + offset,
        )
        page = rows[offset:offset + limit]
        return TicketListResponse(
            total=len(rows),
            items=[self._ticket_to_list_item(t) for t in page],
            limit=limit,
            offset=offset,
        )

    # ── mutate ────────────────────────────────────────────────────────────────

    async def update_status(
        self, ticket_id: str, req: StatusUpdateRequest
    ) -> TicketResponse:
        ticket = await self._store.update_status(
            ticket_id=ticket_id,
            new_status=req.new_status.value,
            comment=req.comment,
            actor_name=req.approver_name,
            actor_email=req.approver_email or "",
        )
        history = await self._store.get_history(ticket_id)
        return self._ticket_to_response(ticket, history)

    async def add_comment(
        self, ticket_id: str, req: CommentRequest
    ) -> None:
        ticket = await self._store.get(ticket_id)
        if not ticket:
            raise KeyError(ticket_id)
        await self._store.add_comment(
            ticket_id, req.author_name, req.author_email or "", req.comment
        )

    # ── stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self) -> TicketStats:
        all_tickets = await self._store.list_tickets(limit=9999)
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for t in all_tickets:
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
            by_type[t.ticket_type.value] = by_type.get(t.ticket_type.value, 0) + 1
        return TicketStats(by_status=by_status, by_type=by_type, total=len(all_tickets))
```

---

## 6. Backend — router implementations

### `main.py`

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.ticket_service import TicketService
from app.routers import tickets, approvals, health

_service: TicketService | None = None


def get_service() -> TicketService:
    assert _service is not None
    return _service


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _service
    _service = TicketService()
    await _service.init()
    yield


app = FastAPI(title="Ticket Webapp API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router, prefix="/api/v1")
app.include_router(tickets.router, prefix="/api/v1")
app.include_router(approvals.router, prefix="/api/v1")
```

### `routers/tickets.py` (key routes)

```python
# app/routers/tickets.py
import csv, io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.main import get_service
from app.schemas import *

router = APIRouter(tags=["tickets"])


@router.post("/tickets/leave", response_model=TicketResponse, status_code=201)
async def create_leave(req: CreateLeaveRequest, svc=Depends(get_service)):
    try:
        return await svc.create_leave(req)
    except ValueError as e:
        raise HTTPException(422, detail=str(e))


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    requester_email: str | None = Query(None),
    status:          str | None = Query(None),
    ticket_type:     str | None = Query(None),
    limit:           int        = Query(50, ge=1, le=200),
    offset:          int        = Query(0, ge=0),
    svc = Depends(get_service),
):
    return await svc.list_tickets(requester_email, status, ticket_type, limit, offset)


@router.get("/tickets/stats", response_model=TicketStats)
async def get_stats(svc=Depends(get_service)):
    return await svc.get_stats()


@router.get("/tickets/export")
async def export_csv(
    requester_email: str | None = Query(None),
    status:          str | None = Query(None),
    ticket_type:     str | None = Query(None),
    svc = Depends(get_service),
):
    result = await svc.list_tickets(requester_email, status, ticket_type, 9999, 0)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "ticket_id","ticket_type","title","requester_name","requester_email",
        "status","priority","created_at","updated_at",
    ])
    writer.writeheader()
    for item in result.items:
        writer.writerow(item.model_dump(exclude={"extra_fields","history"}))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tickets.csv"},
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, svc=Depends(get_service)):
    try:
        return await svc.get_ticket(ticket_id)
    except KeyError:
        raise HTTPException(404, detail=f"Ticket {ticket_id} không tồn tại")


@router.patch("/tickets/{ticket_id}/status", response_model=TicketResponse)
async def update_status(ticket_id: str, req: StatusUpdateRequest, svc=Depends(get_service)):
    try:
        return await svc.update_status(ticket_id, req)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, detail=str(e))


@router.post("/tickets/{ticket_id}/comments", status_code=204)
async def add_comment(ticket_id: str, req: CommentRequest, svc=Depends(get_service)):
    try:
        await svc.add_comment(ticket_id, req)
    except KeyError:
        raise HTTPException(404, detail=f"Ticket {ticket_id} không tồn tại")
```

### `config.py`

```python
# app/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ticket_db_path: str  = "../ticket-mcp-server/data/tickets.db"
    mcp_server_path: str = "../ticket-mcp-server"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:80"]

    class Config:
        env_file = ".env"

settings = Settings()
```

### `requirements.txt`

```
fastapi>=0.111
uvicorn[standard]>=0.29
pydantic>=2.7
pydantic-settings>=2.2
aiosqlite>=0.20
python-dotenv>=1.0
```

---

## 7. Frontend components spec

### Tech stack

- **React 18** + **TypeScript**
- **Vite** dev server (proxy `/api` → `localhost:8000`)
- **Zustand** for global state (user profile, role, filters)
- **SWR** for data fetching with automatic revalidation
- **Tailwind CSS** + **shadcn/ui** component library
- **React Hook Form** + **Zod** for form validation
- **Tabler Icons** (`@tabler/icons-react`) for iconography

### User profile setup (first launch)

Shown as a blocking modal before any page renders. Saves to `localStorage` under key `ticket_user_profile`.

```typescript
interface UserProfile {
  name:  string;    // required
  email: string;    // required, validated as email
  role:  "employee" | "manager" | "admin";
}
```

The profile can be edited later via the header avatar menu. Since there is no auth, role is self-selected.

### Zustand store (`store/index.ts`)

```typescript
interface AppStore {
  profile:     UserProfile | null;
  setProfile:  (p: UserProfile) => void;

  filters: {
    status:     string;
    ticketType: string;
    search:     string;    // matches requester_email or title
  };
  setFilter: (key: keyof AppStore["filters"], value: string) => void;
  resetFilters: () => void;
}
```

### `useTickets.ts` — SWR hook

```typescript
// hooks/useTickets.ts
import useSWR from "swr";
import { ticketApi } from "@/api/ticketApi";

export function useTickets(params: TicketListParams) {
  return useSWR(
    ["tickets", params],
    () => ticketApi.listTickets(params),
    { refreshInterval: 15_000 }   // poll every 15s
  );
}

export function useTicket(ticketId: string | null) {
  return useSWR(
    ticketId ? ["ticket", ticketId] : null,
    () => ticketApi.getTicket(ticketId!)
  );
}
```

### `TicketList.tsx`

```
┌─────────────────────────────────────────────────────────────────┐
│  [+ Tạo yêu cầu]                                [👤 Nguyễn Duy] │
├─────────────────────────────────────────────────────────────────┤
│  🔍 [search box]                                                 │
│  Loại: [Tất cả] [Nghỉ phép] [Công tác] [Làm thêm giờ] [...]    │
│  Trạng thái: [Tất cả ▾]                                          │
├──────┬──────────────────────────┬──────────┬────────┬───────────┤
│  ID  │  Tiêu đề                 │  Loại    │ Trạng  │  Ngày tạo │
│      │                          │          │  thái  │           │
├──────┼──────────────────────────┼──────────┼────────┼───────────┤
│ TKT- │ Nghỉ phép — annual ...   │ 📅 Nghỉ  │ 🟡 Chờ │ 07/06/26  │
│ 0001 │                          │  phép    │        │           │
└──────┴──────────────────────────┴──────────┴────────┴───────────┘
```

Clicking any row opens `TicketDetail` as a side sheet (right-sliding panel).

### `NewTicketModal.tsx` — 3-step wizard

**Step 1 — Choose type** (icon grid):

```
  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │  📅         │  │  ✈️         │  │  ⏰         │
  │ Nghỉ phép  │  │ Công tác   │  │Làm thêm giờ│
  └────────────┘  └────────────┘  └────────────┘
  ┌────────────┐  ┌────────────┐  ┌────────────┐
  │  💻         │  │  📚         │  │  📝         │
  │Yêu cầu TB  │  │  Đào tạo   │  │    Khác    │
  └────────────┘  └────────────┘  └────────────┘
```

**Step 2 — Type-specific form** (see form specs below)

**Step 3 — Confirmation**:
```
  ✅ Yêu cầu đã được tạo thành công!
  Mã ticket: TKT-20260607-0003
  Trạng thái: Chờ phê duyệt
  [Xem chi tiết]  [Tạo yêu cầu khác]
```

### Form field specifications

**`LeaveForm.tsx`**

| Field | Type | Validation | Label |
|-------|------|------------|-------|
| `leave_type` | select | required | Loại nghỉ |
| `start_date` | date picker | required | Ngày bắt đầu |
| `end_date` | date picker | >= start_date | Ngày kết thúc |
| `reason` | textarea | required, min 10 chars | Lý do |
| `handover_person` | text input | optional | Người bàn giao |

Shows computed "Số ngày nghỉ: X" when both dates are selected.

**`TripForm.tsx`**

| Field | Type | Validation | Label |
|-------|------|------------|-------|
| `destination` | text | required | Điểm đến |
| `purpose` | textarea | required | Mục đích |
| `start_date` | date picker | required | Ngày đi |
| `end_date` | date picker | >= start | Ngày về |
| `transport_mode` | select | optional | Phương tiện |
| `estimated_budget_vnd` | number | >= 0 | Ngân sách dự kiến (VND) |

**`OvertimeForm.tsx`**

| Field | Type | Validation | Label |
|-------|------|------------|-------|
| `date` | date picker | required | Ngày làm thêm |
| `hours` | number | 0 < x ≤ 12, step 0.5 | Số giờ |
| `reason` | textarea | required | Lý do |
| `project_code` | text | optional | Mã dự án |

**`EquipmentForm.tsx`**

| Field | Type | Validation | Label |
|-------|------|------------|-------|
| `item_type` | text | required | Loại thiết bị |
| `quantity` | number | >= 1 | Số lượng |
| `justification` | textarea | required | Lý do yêu cầu |
| `description` | textarea | optional | Mô tả thêm |

**`TrainingForm.tsx`**

| Field | Type | Validation | Label |
|-------|------|------------|-------|
| `course_name` | text | required | Tên khóa học |
| `provider` | text | required | Đơn vị tổ chức |
| `start_date` | date picker | required | Ngày bắt đầu |
| `end_date` | date picker | >= start | Ngày kết thúc |
| `cost_vnd` | number | >= 0 | Chi phí (VND) |

### `TicketDetail.tsx`

```
┌────────────────────────────────────────────────────────────┐
│  TKT-20260607-0003                              [✕ Đóng]  │
│  Nghỉ phép — annual (2026-07-01 → 2026-07-05)             │
│                                                             │
│  Loại: 📅 Nghỉ phép năm     Trạng thái: 🟡 Chờ phê duyệt  │
│  Người yêu cầu: Nguyễn Duy                                 │
│  Ngày tạo: 07/06/2026 14:32                                │
│                                                             │
│  ── Thông tin chi tiết ──────────────────────────────────  │
│  Ngày bắt đầu:  01/07/2026                                 │
│  Ngày kết thúc: 05/07/2026                                 │
│  Số ngày:       5                                          │
│  Lý do:         Nghỉ hè gia đình                           │
│  Bàn giao cho:  Trần Văn B                                 │
│                                                             │
│  ── Thao tác ────────────────────────────────────────────  │
│  [✓ Phê duyệt]  [✗ Từ chối]  [⊘ Hủy]                    │
│  Ghi chú: _______________________________________________  │
│                                                             │
│  ── Lịch sử ─────────────────────────────────────────────  │
│  ● 07/06/2026 14:32 · Nguyễn Duy tạo ticket               │
│    Trạng thái: → pending                                   │
└────────────────────────────────────────────────────────────┘
```

Action buttons are shown conditionally:
- "Phê duyệt" + "Từ chối" → only if `status === "pending"` AND role is `manager` or `admin`
- "Hủy" → only if `status` is in `["draft","pending","approved"]` AND requester_email matches current user (or role is admin)
- "Hoàn thành" → only if `status === "approved"` AND role is `admin`

### `ApprovalPanel.tsx`

Full page for managers. Filters to `status=pending` only. Each row has inline approve/reject.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ⏳ Chờ phê duyệt (4)                                                    │
├────────────┬────────────────────────┬─────────────┬──────────┬──────────┤
│  Người yêu │  Tiêu đề               │  Loại       │  Ngày tạo│  Thao tác│
│  cầu       │                        │             │          │          │
├────────────┼────────────────────────┼─────────────┼──────────┼──────────┤
│ Nguyễn Duy │ Nghỉ phép — annual ... │ 📅 Nghỉ phép│ 07/06/26 │ [✓] [✗] │
├────────────┼────────────────────────┼─────────────┼──────────┼──────────┤
│ ...        │                        │             │          │          │
└────────────┴────────────────────────┴─────────────┴──────────┴──────────┘
```

Clicking `[✓]` or `[✗]` opens an inline comment input before confirming.

### `TicketBadge.tsx`

```typescript
const STATUS_CONFIG = {
  draft:     { label: "Nháp",           bg: "bg-gray-100",   text: "text-gray-600"  },
  pending:   { label: "Chờ phê duyệt",  bg: "bg-amber-100",  text: "text-amber-700" },
  approved:  { label: "Đã phê duyệt",   bg: "bg-green-100",  text: "text-green-700" },
  rejected:  { label: "Từ chối",        bg: "bg-red-100",    text: "text-red-700"   },
  cancelled: { label: "Đã hủy",         bg: "bg-gray-100",   text: "text-gray-500"  },
  completed: { label: "Hoàn thành",     bg: "bg-blue-100",   text: "text-blue-700"  },
};

const TYPE_CONFIG = {
  leave:     { label: "Nghỉ phép",    icon: "📅" },
  trip:      { label: "Công tác",     icon: "✈️"  },
  overtime:  { label: "Làm thêm giờ", icon: "⏰" },
  equipment: { label: "Yêu cầu TB",   icon: "💻" },
  training:  { label: "Đào tạo",      icon: "📚" },
  other:     { label: "Khác",         icon: "📝" },
};
```

---

## 8. Vietnamese UI labels (full mapping)

### Page titles

| Key | Vietnamese |
|-----|-----------|
| page.myTickets | Yêu cầu của tôi |
| page.allTickets | Tất cả yêu cầu |
| page.approvals | Phê duyệt |

### Navigation

| Key | Vietnamese |
|-----|-----------|
| nav.myTickets | Yêu cầu của tôi |
| nav.approvals | Chờ phê duyệt |
| nav.allTickets | Tất cả yêu cầu |
| nav.profile | Hồ sơ cá nhân |
| nav.logout | Đăng xuất |

### Buttons / actions

| Key | Vietnamese |
|-----|-----------|
| btn.createTicket | + Tạo yêu cầu |
| btn.approve | Phê duyệt |
| btn.reject | Từ chối |
| btn.cancel | Hủy yêu cầu |
| btn.complete | Hoàn thành |
| btn.addComment | Thêm ghi chú |
| btn.save | Lưu |
| btn.close | Đóng |
| btn.back | Quay lại |
| btn.next | Tiếp theo |
| btn.submit | Gửi yêu cầu |
| btn.export | Xuất CSV |
| btn.confirm | Xác nhận |

### Form labels

| Key | Vietnamese |
|-----|-----------|
| form.requesterName | Họ và tên |
| form.requesterEmail | Email |
| form.priority | Độ ưu tiên |
| form.leaveType | Loại nghỉ |
| form.startDate | Ngày bắt đầu |
| form.endDate | Ngày kết thúc |
| form.numDays | Số ngày |
| form.reason | Lý do |
| form.handoverPerson | Người bàn giao |
| form.destination | Điểm đến |
| form.purpose | Mục đích |
| form.transportMode | Phương tiện |
| form.budget | Ngân sách dự kiến (VND) |
| form.otDate | Ngày làm thêm |
| form.hours | Số giờ |
| form.projectCode | Mã dự án |
| form.itemType | Loại thiết bị |
| form.quantity | Số lượng |
| form.justification | Lý do yêu cầu |
| form.courseName | Tên khóa học |
| form.provider | Đơn vị tổ chức |
| form.cost | Chi phí (VND) |
| form.description | Mô tả thêm |
| form.comment | Ghi chú |
| form.approverName | Người phê duyệt |

### Ticket type names

| Key | Vietnamese |
|-----|-----------|
| type.leave | Nghỉ phép |
| type.trip | Công tác |
| type.overtime | Làm thêm giờ |
| type.equipment | Yêu cầu thiết bị |
| type.training | Đào tạo |
| type.other | Khác |

### Leave type names

| Key | Vietnamese |
|-----|-----------|
| leaveType.annual | Nghỉ phép năm |
| leaveType.sick | Nghỉ ốm |
| leaveType.personal | Nghỉ việc riêng |
| leaveType.unpaid | Nghỉ không lương |
| leaveType.maternity | Nghỉ thai sản (nữ) |
| leaveType.paternity | Nghỉ thai sản (nam) |

### Transport mode names

| Key | Vietnamese |
|-----|-----------|
| transport.plane | Máy bay |
| transport.train | Tàu hỏa |
| transport.car | Ô tô |
| transport.other | Khác |

### Status names

| Key | Vietnamese |
|-----|-----------|
| status.draft | Nháp |
| status.pending | Chờ phê duyệt |
| status.approved | Đã phê duyệt |
| status.rejected | Từ chối |
| status.cancelled | Đã hủy |
| status.completed | Hoàn thành |

### Priority names

| Key | Vietnamese |
|-----|-----------|
| priority.low | Thấp |
| priority.normal | Bình thường |
| priority.high | Cao |
| priority.urgent | Khẩn cấp |

### Filter / table labels

| Key | Vietnamese |
|-----|-----------|
| filter.all | Tất cả |
| filter.status | Trạng thái |
| filter.type | Loại yêu cầu |
| filter.search | Tìm kiếm... |
| table.ticketId | Mã yêu cầu |
| table.title | Tiêu đề |
| table.type | Loại |
| table.status | Trạng thái |
| table.requester | Người yêu cầu |
| table.createdAt | Ngày tạo |
| table.actions | Thao tác |
| table.empty | Không có yêu cầu nào. |

### History action labels

| Key | Vietnamese |
|-----|-----------|
| history.created | Tạo yêu cầu |
| history.status_changed | Thay đổi trạng thái |
| history.comment_added | Thêm ghi chú |

### Validation messages

| Key | Vietnamese |
|-----|-----------|
| validation.required | Trường này là bắt buộc |
| validation.emailInvalid | Email không hợp lệ |
| validation.endBeforeStart | Ngày kết thúc phải sau ngày bắt đầu |
| validation.hoursRange | Số giờ phải từ 0.5 đến 12 |
| validation.quantityMin | Số lượng phải ít nhất là 1 |

### Profile modal

| Key | Vietnamese |
|-----|-----------|
| profile.title | Thông tin cá nhân |
| profile.subtitle | Vui lòng nhập thông tin để bắt đầu sử dụng |
| profile.name | Họ và tên |
| profile.email | Địa chỉ email |
| profile.role | Vai trò |
| profile.role.employee | Nhân viên |
| profile.role.manager | Quản lý |
| profile.role.admin | Quản trị viên |
| profile.save | Bắt đầu |

---

## 9. `docker-compose.yml`

```yaml
# docker-compose.yml
version: "3.9"

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      TICKET_DB_PATH: /data/tickets.db
      MCP_SERVER_PATH: /mcp
      CORS_ORIGINS: '["http://localhost", "http://localhost:80"]'
    volumes:
      # Shared SQLite database (same file used by Claude Desktop MCP server)
      - ticket_db:/data
      # Mount ticket-mcp-server so the backend can import it
      - ../ticket-mcp-server:/mcp:ro
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  ticket_db:
    # Bind to host path so Claude Desktop MCP server shares it:
    # driver_opts:
    #   type: none
    #   device: /absolute/path/to/ticket-mcp-server/data
    #   o: bind
```

**`backend/Dockerfile`**:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`frontend/Dockerfile`** (multi-stage):

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

**`frontend/nginx.conf`** (SPA routing + proxy):

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # Proxy API calls to backend
    location /api/ {
        proxy_pass http://backend:8000;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 10. Environment variables

**`backend/.env.example`**:

```env
# Path to the SQLite database (shared with ticket-mcp-server)
TICKET_DB_PATH=../../ticket-mcp-server/data/tickets.db

# Absolute or relative path to ticket-mcp-server directory (for sys.path injection)
MCP_SERVER_PATH=../../ticket-mcp-server

# Comma-separated allowed CORS origins
CORS_ORIGINS=["http://localhost:5173","http://localhost:80"]
```

**`frontend/.env.example`**:

```env
# Base URL for the API (used in development; in prod, nginx proxies /api/)
VITE_API_BASE_URL=http://localhost:8000
```

---

## 11. Implementation order

Work through these in sequence. Each step produces working, testable code before moving on.

1. **`ticket-webapp/` scaffold** — create directory structure, `package.json`, `vite.config.ts`, `tsconfig.json`, `requirements.txt`, `.env.example` files.

2. **`backend/app/config.py`** — `Settings` class with pydantic-settings. Verify it reads `.env`.

3. **`backend/app/schemas.py`** — all Pydantic request/response models. No logic, just data shapes. Run `python -c "from app.schemas import *"` to verify imports.

4. **`backend/app/services/ticket_service.py`** — `sys.path` injection + `TicketService` class with all methods stubbed (`raise NotImplementedError`). Confirm `SqliteStore` imports successfully.

5. **Implement `TicketService` methods** — `init`, `create_leave`, `create_trip`, `create_overtime`, `create_equipment`, `create_training`, `create_generic`, `get_ticket`, `list_tickets`, `update_status`, `add_comment`, `get_stats`. Test each with a quick `asyncio.run()` script.

6. **`backend/app/routers/health.py`** — trivial health check. Wire into `main.py`.

7. **`backend/app/routers/tickets.py`** — all CRUD + stats + export endpoints. Start `uvicorn` and test via `curl` or FastAPI's `/docs`.

8. **`backend/app/routers/approvals.py`** — convenience endpoint `GET /approvals/pending` that wraps `list_tickets(status="pending")`. Managers can also use it from the generic tickets endpoint.

9. **`backend/app/main.py`** — `lifespan`, CORS middleware, router registration. End-to-end: create a leave ticket, list it, approve it.

10. **`frontend/src/api/ticketApi.ts`** — all typed fetch wrappers. No React yet — just functions that call the backend. Test by running `ts-node` or using the browser console.

11. **`frontend/src/store/index.ts`** — Zustand store: `UserProfile`, filters. Include `localStorage` persistence for the profile.

12. **`frontend/src/hooks/useTickets.ts`** — SWR hooks for list and single ticket.

13. **`frontend/src/components/tickets/TicketBadge.tsx`** — purely visual, no data deps. Renders status and type badges with correct colors.

14. **`frontend/src/components/tickets/TicketCard.tsx`** — single row/card using `TicketBadge`.

15. **`frontend/src/components/tickets/TicketList.tsx`** — filter bar + table using `useTickets` + `TicketCard`. Implement filter state wired to Zustand.

16. **`frontend/src/components/tickets/TicketDetail.tsx`** — side sheet with full details, history timeline, and action buttons.

17. **Profile modal** (inline in `App.tsx` initially) — blocks render until `profile` exists in Zustand.

18. **`frontend/src/components/forms/LeaveForm.tsx`** — React Hook Form + Zod, all fields, date validation, computed num_days display.

19. **`frontend/src/components/forms/TripForm.tsx`**, **`OvertimeForm.tsx`**, **`EquipmentForm.tsx`**, **`TrainingForm.tsx`**, **`GenericForm.tsx`** — same pattern.

20. **`frontend/src/components/forms/NewTicketModal.tsx`** — 3-step wizard: type selector → form component → confirmation. Wire to `ticketApi.create*` calls. Invalidate SWR cache on success.

21. **`frontend/src/components/approvals/ApprovalPanel.tsx`** — pending-only list with inline approve/reject + comment. Wire to `PATCH /tickets/{id}/status`.

22. **`frontend/src/pages/MyTicketsPage.tsx`** — `TicketList` pre-filtered to `requester_email = profile.email`.

23. **`frontend/src/pages/ApprovalsPage.tsx`** — `ApprovalPanel` wrapped in page layout. Guard: only show in nav if role is `manager` or `admin`.

24. **`frontend/src/pages/AllTicketsPage.tsx`** — `TicketList` with no email pre-filter + export CSV button. Guard: only for `admin`.

25. **`frontend/src/components/layout/AppShell.tsx`** + **`Header.tsx`** — nav sidebar/top bar with role-conditional menu items.

26. **`frontend/src/App.tsx`** — router setup (React Router), page assembly, profile guard.

27. **`docker-compose.yml`** + **Dockerfiles** + **`nginx.conf`** — containerize. Run `docker compose up`, confirm full stack works on `:80`.

28. **End-to-end verification** — manually submit a leave ticket as employee, approve it as manager, see status update reflected in MyTicketsPage and AllTicketsPage. Confirm the same ticket is visible in Claude Desktop via `list_tickets`.

---

## 12. Known limitations and v2 improvements

| Item | Status | Notes |
|------|--------|-------|
| `SqliteStore.list_tickets` has no native `OFFSET` | Workaround in service layer | Add `OFFSET ?` to SQL query in v2 |
| No real authentication | By design for v1 | Add JWT / OAuth2 in v2 |
| Approver assignment not modelled | All pending tickets visible to all managers | Add `assigned_to` column in v2 |
| `list_tickets` total count is approximate | Fetches `limit+offset` rows | For true pagination, add `SELECT COUNT(*)` query |
| No websocket / push | 15s SWR polling | Add FastAPI WebSocket or SSE for live updates in v2 |
| CSV export fetches up to 9999 rows | Fine for small teams | Add streaming export for large datasets |
