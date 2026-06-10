# Ticket MCP Server

A standalone MCP server that exposes workplace ticket creation and management as tools callable by Claude. Covers six ticket types common to Vietnamese-language workplaces.

## What it does

- Create, view, list, and update approval status for workplace tickets
- Supports: nghỉ phép (leave), công tác (business trip), làm thêm giờ (overtime), yêu cầu thiết bị (equipment), đào tạo (training), khác (other)
- All tool responses are pre-formatted Vietnamese strings — Claude relays them directly
- Ticket IDs: `TKT-YYYYMMDD-NNNN` (e.g. `TKT-20260607-0001`)
- Persistent SQLite storage in `data/tickets.db`

## Prerequisites

- Python 3.11+
- pip

## Setup

```bash
cd ticket-mcp-server

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env if you want a custom DB path

# Run the server (for testing)
python server.py
```

## Claude Desktop configuration

Add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

macOS / Linux:

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

Restart Claude Desktop after saving. All 11 tools appear automatically.

## Tools reference

### Generic tools

| Tool | Description | Key parameters |
|------|-------------|----------------|
| `create_ticket` | Create any ticket type | `ticket_type`, `title`, `description`, `requester_name`, `requester_email`, `priority`, `extra_fields` (JSON string) |
| `get_ticket` | Get full ticket details | `ticket_id` |
| `list_tickets` | List tickets with filters | `requester_email`, `status`, `ticket_type`, `limit` |
| `update_ticket_status` | Approve/reject/cancel/complete | `ticket_id`, `new_status`, `comment`, `approver_name`, `approver_email` |
| `add_comment` | Add a comment without status change | `ticket_id`, `author_name`, `comment`, `author_email` |
| `get_ticket_types` | List supported ticket types and required fields | — |
| `get_ticket_statuses` | List valid statuses and transitions | — |
| `get_pending_approvals` | List all pending tickets | `approver_email` (optional) |

### Type-specific tools

| Tool | Description | Key parameters |
|------|-------------|----------------|
| `create_leave_request` | Create a leave request | `requester_name`, `requester_email`, `leave_type`, `start_date`, `end_date`, `reason`, `handover_person` |
| `create_trip_request` | Create a business trip request | `requester_name`, `requester_email`, `destination`, `purpose`, `start_date`, `end_date`, `estimated_budget_vnd`, `transport_mode` |
| `create_overtime_request` | Create an overtime request | `requester_name`, `requester_email`, `date`, `hours`, `reason`, `project_code` |

### Status transitions

```
draft      → pending, cancelled
pending    → approved, rejected, cancelled
approved   → completed, cancelled
rejected   → pending (resubmit), cancelled
cancelled  → (terminal)
completed  → (terminal)
```

### Leave types

`annual` · `sick` · `personal` · `unpaid` · `maternity` · `paternity`

### Transport modes (trip)

`plane` · `train` · `car` · `other`

## Example conversations

### 1. Employee creates a leave request

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
✅ Đã tạo yêu cầu nghỉ phép TKT-20260607-0001
Loại: Nghỉ phép năm
Từ: 10/06/2026 đến 12/06/2026 (3 ngày)
Trạng thái: Chờ phê duyệt
```

### 2. Employee checks ticket status

```
User:  Đơn nghỉ phép của tôi đến đâu rồi? Email tôi là a.nguyen@company.vn.

Claude: [calls list_tickets(
           requester_email="a.nguyen@company.vn",
           ticket_type="leave",
           status="pending",
         )]

Tool returns:
📋 Danh sách ticket (1 kết quả)
1. TKT-20260607-0001 — Nghỉ phép — Nghỉ phép năm (2026-06-10 → 2026-06-12) [pending] — Nguyễn Văn A (07/06/2026)
```

### 3. Manager approves a ticket

```
User:  Tôi là Trần Thị B, quản lý. Duyệt đơn TKT-20260607-0001.

Claude: [calls update_ticket_status(
           ticket_id="TKT-20260607-0001",
           new_status="approved",
           comment="Đã xác nhận với nhân viên về người bàn giao",
           approver_name="Trần Thị B",
           approver_email="b.tran@company.vn",
         )]

Tool returns:
✅ TKT-20260607-0001 đã được cập nhật → approved
Bởi: Trần Thị B
Ghi chú: Đã xác nhận với nhân viên về người bàn giao
```

## Integration with new-rag-2026

Connect as an MCP subprocess client (Option B from PLAN.md):

```python
# new-rag-2026/agents/procedures_agent.py
from mcp_client import McpClient

ticket_client = McpClient(
    command=["python", "/path/to/ticket-mcp-server/server.py"]
)

result = await ticket_client.call_tool("create_leave_request", {
    "requester_name": "Nguyễn Văn A",
    "requester_email": "a.nguyen@company.vn",
    "leave_type": "annual",
    "start_date": "2026-06-10",
    "end_date": "2026-06-12",
    "reason": "Du lịch gia đình",
})
```
