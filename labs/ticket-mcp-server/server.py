"""Ticket MCP Server — workplace ticket creation and management."""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from config import settings                      # noqa: E402
from storage.sqlite_store import SqliteStore    # noqa: E402
import tools.ticket_tools as _tt               # noqa: E402
import tools.leave_tools as _lt                # noqa: E402
import tools.trip_tools as _trp               # noqa: E402
import tools.overtime_tools as _ot             # noqa: E402

mcp = FastMCP("ticket-server")

# Inject shared store into all tool modules
store = SqliteStore(settings.db_path)
_tt.store = store
_lt.store = store
_trp.store = store
_ot.store = store


# ---------------------------------------------------------------------------
# Generic ticket tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_ticket(
    ticket_type: str,
    title: str,
    description: str,
    requester_name: str,
    requester_email: str,
    priority: str = "normal",
    extra_fields: str = "{}",
) -> str:
    """
    Tạo một ticket mới. Dùng công cụ này khi không có công cụ chuyên biệt cho loại yêu cầu.

    ticket_type must be one of: leave | trip | overtime | equipment | training | other
    priority must be one of: low | normal | high | urgent
    extra_fields: JSON string with any additional type-specific key/value pairs.

    Returns a confirmation string with ticket_id and status.
    """
    return await _tt.create_ticket(
        ticket_type=ticket_type,
        title=title,
        description=description,
        requester_name=requester_name,
        requester_email=requester_email,
        priority=priority,
        extra_fields=extra_fields,
    )


@mcp.tool()
async def get_ticket(ticket_id: str) -> str:
    """
    Lấy thông tin chi tiết của một ticket theo ID.

    ticket_id: ticket identifier in format TKT-YYYYMMDD-NNNN

    Returns full ticket details including status, fields, and history.
    Returns an error message if ticket_id does not exist.
    """
    return await _tt.get_ticket(ticket_id=ticket_id)


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
    """
    return await _tt.list_tickets(
        requester_email=requester_email,
        status=status,
        ticket_type=ticket_type,
        limit=limit,
    )


@mcp.tool()
async def update_ticket_status(
    ticket_id: str,
    new_status: str,
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
    """
    return await _tt.update_ticket_status(
        ticket_id=ticket_id,
        new_status=new_status,
        comment=comment,
        approver_name=approver_name,
        approver_email=approver_email,
    )


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
    """
    return await _tt.add_comment(
        ticket_id=ticket_id,
        author_name=author_name,
        comment=comment,
        author_email=author_email,
    )


@mcp.tool()
async def get_ticket_types() -> str:
    """
    Trả về danh sách tất cả loại ticket được hỗ trợ và các trường bắt buộc.

    Use this tool to understand what ticket types exist before creating one.
    """
    return await _tt.get_ticket_types()


@mcp.tool()
async def get_ticket_statuses() -> str:
    """
    Trả về danh sách trạng thái hợp lệ và các chuyển đổi được phép.

    Use this before calling update_ticket_status to check valid transitions.
    """
    return await _tt.get_ticket_statuses()


@mcp.tool()
async def get_pending_approvals(approver_email: str = "") -> str:
    """
    Lấy danh sách ticket đang chờ phê duyệt.

    approver_email: optional — currently returns all pending tickets.
    Returns a list of tickets needing action.
    """
    return await _tt.get_pending_approvals(approver_email=approver_email)


# ---------------------------------------------------------------------------
# Type-specific tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_leave_request(
    requester_name: str,
    requester_email: str,
    leave_type: str,
    start_date: str,
    end_date: str,
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
    """
    return await _lt.create_leave_request(
        requester_name=requester_name,
        requester_email=requester_email,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        handover_person=handover_person,
    )


@mcp.tool()
async def create_trip_request(
    requester_name: str,
    requester_email: str,
    destination: str,
    purpose: str,
    start_date: str,
    end_date: str,
    estimated_budget_vnd: int = 0,
    transport_mode: str = "",
) -> str:
    """
    Tạo yêu cầu công tác. Sử dụng khi nhân viên cần đăng ký chuyến công tác.

    destination: city or country of travel (required)
    purpose: business justification (required)
    start_date / end_date: YYYY-MM-DD. end_date >= start_date.
    estimated_budget_vnd: estimated cost in VND (0 = not specified)
    transport_mode: plane | train | car | other (optional)
    """
    return await _trp.create_trip_request(
        requester_name=requester_name,
        requester_email=requester_email,
        destination=destination,
        purpose=purpose,
        start_date=start_date,
        end_date=end_date,
        estimated_budget_vnd=estimated_budget_vnd,
        transport_mode=transport_mode,
    )


@mcp.tool()
async def create_overtime_request(
    requester_name: str,
    requester_email: str,
    date: str,
    hours: float,
    reason: str,
    project_code: str = "",
) -> str:
    """
    Tạo yêu cầu làm thêm giờ. Sử dụng khi nhân viên cần đăng ký OT.

    date: YYYY-MM-DD date of overtime work
    hours: number of overtime hours (must be > 0 and <= 12)
    reason: business reason for overtime (required)
    project_code: optional project or cost-center code
    """
    return await _ot.create_overtime_request(
        requester_name=requester_name,
        requester_email=requester_email,
        date=date,
        hours=hours,
        reason=reason,
        project_code=project_code,
    )


# ---------------------------------------------------------------------------
# Startup & entry point
# ---------------------------------------------------------------------------

async def _startup() -> None:
    """Initialize the database before the server starts accepting requests."""
    await store.init_db()


if __name__ == "__main__":
    asyncio.run(_startup())
    mcp.run()   # stdio transport (default)
