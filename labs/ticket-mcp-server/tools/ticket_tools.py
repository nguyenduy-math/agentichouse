"""Generic ticket tools: create, get, list, update status, comment, and lookups."""

import json
from typing import TYPE_CHECKING

from models.ticket import TicketCreate, TicketType, TicketPriority

if TYPE_CHECKING:
    from storage.sqlite_store import SqliteStore

# Injected by server.py before mcp.run()
store: "SqliteStore | None" = None


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
    Example: "✅ Ticket TKT-20260607-0001 đã được tạo\\nLoại: other\\nTrạng thái: Chờ phê duyệt"
    """
    try:
        tt = TicketType(ticket_type)
    except ValueError:
        return f"❌ Loại ticket không hợp lệ: '{ticket_type}'. Các giá trị hợp lệ: {[t.value for t in TicketType]}"

    try:
        prio = TicketPriority(priority)
    except ValueError:
        return f"❌ Độ ưu tiên không hợp lệ: '{priority}'. Các giá trị hợp lệ: {[p.value for p in TicketPriority]}"

    try:
        extra = json.loads(extra_fields)
    except json.JSONDecodeError as e:
        return f"❌ extra_fields không phải JSON hợp lệ: {e}"

    data = TicketCreate(
        ticket_type=tt,
        title=title,
        description=description,
        requester_name=requester_name,
        requester_email=requester_email,
        priority=prio,
        extra_fields=extra,
    )
    ticket = await store.create(data)
    return (
        f"✅ Ticket {ticket.ticket_id} đã được tạo\n"
        f"Loại: {ticket.ticket_type.value}\n"
        f"Tiêu đề: {ticket.title}\n"
        f"Người yêu cầu: {ticket.requester_name}\n"
        f"Trạng thái: Chờ phê duyệt"
    )


async def get_ticket(ticket_id: str) -> str:
    """
    Lấy thông tin chi tiết của một ticket theo ID.

    ticket_id: ticket identifier in format TKT-YYYYMMDD-NNNN

    Returns full ticket details including status, fields, and history.
    Returns an error message if ticket_id does not exist.
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

    if ticket.description:
        lines.append(f"Mô tả: {ticket.description}")

    if ticket.extra_fields:
        lines.append("\nThông tin bổ sung:")
        for k, v in ticket.extra_fields.items():
            lines.append(f"  {k}: {v}")

    if history:
        lines.append("\nLịch sử:")
        for h in history:
            entry = (
                f"  - {h.timestamp.strftime('%d/%m/%Y %H:%M')} "
                f"[{h.action}] bởi {h.actor_name}"
            )
            if h.action == "status_changed" and h.old_value and h.new_value:
                entry += f": {h.old_value} → {h.new_value}"
            if h.comment:
                entry += f" — {h.comment}"
            lines.append(entry)

    return "\n".join(lines)


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
    try:
        ticket = await store.update_status(
            ticket_id=ticket_id,
            new_status=new_status,
            comment=comment,
            actor_name=approver_name or "System",
            actor_email=approver_email,
        )
        result = (
            f"✅ {ticket.ticket_id} đã được cập nhật → {ticket.status.value}\n"
            f"Bởi: {approver_name or 'System'}"
        )
        if comment:
            result += f"\nGhi chú: {comment}"
        return result
    except ValueError as e:
        return f"❌ Lỗi: {e}"


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
    ticket = await store.get(ticket_id)
    if not ticket:
        return f"❌ Không tìm thấy ticket {ticket_id}"
    await store.add_comment(ticket_id, author_name, author_email, comment)
    return f"💬 Đã thêm ghi chú vào {ticket_id}"


async def get_ticket_types() -> str:
    """
    Trả về danh sách tất cả loại ticket được hỗ trợ và các trường bắt buộc.

    Use this tool to understand what ticket types exist before creating one.
    Returns a formatted list of ticket types with their required fields.
    """
    return """📂 Các loại ticket được hỗ trợ:

1. leave (Nghỉ phép)
   Công cụ chuyên biệt: create_leave_request
   Trường bắt buộc: leave_type, start_date, end_date, reason
   Loại nghỉ: annual | sick | personal | unpaid | maternity | paternity

2. trip (Công tác)
   Công cụ chuyên biệt: create_trip_request
   Trường bắt buộc: destination, purpose, start_date, end_date
   Tùy chọn: estimated_budget_vnd, transport_mode

3. overtime (Làm thêm giờ)
   Công cụ chuyên biệt: create_overtime_request
   Trường bắt buộc: date, hours, reason
   Tùy chọn: project_code

4. equipment (Yêu cầu thiết bị)
   Sử dụng create_ticket với ticket_type=equipment
   Trường bắt buộc trong extra_fields: item_type, quantity, justification

5. training (Đào tạo)
   Sử dụng create_ticket với ticket_type=training
   Trường bắt buộc trong extra_fields: course_name, provider, start_date, end_date
   Tùy chọn: cost_vnd

6. other (Khác)
   Sử dụng create_ticket với ticket_type=other
   Mô tả chi tiết trong description"""


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


async def get_pending_approvals(approver_email: str = "") -> str:
    """
    Lấy danh sách ticket đang chờ phê duyệt.

    approver_email: if provided, returns all pending tickets (to be filtered by manager).
    Currently returns all tickets with status=pending since approver assignment
    is not yet modelled.

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
