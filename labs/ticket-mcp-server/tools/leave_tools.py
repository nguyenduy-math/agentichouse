"""Leave request tool with type-specific validation."""

from datetime import date
from typing import TYPE_CHECKING

from models.ticket import TicketCreate, TicketType, LeaveType

if TYPE_CHECKING:
    from storage.sqlite_store import SqliteStore

# Injected by server.py
store: "SqliteStore | None" = None

LEAVE_LABELS: dict[str, str] = {
    "annual":    "Nghỉ phép năm",
    "sick":      "Nghỉ ốm",
    "personal":  "Nghỉ việc riêng",
    "unpaid":    "Nghỉ không lương",
    "maternity": "Nghỉ thai sản (nữ)",
    "paternity": "Nghỉ thai sản (nam)",
}


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

    Returns confirmation with ticket_id, leave type, dates, number of days, and status.
    """
    # Validate leave_type
    try:
        lt = LeaveType(leave_type)
    except ValueError:
        valid = ", ".join(v.value for v in LeaveType)
        return f"❌ Loại nghỉ không hợp lệ: '{leave_type}'. Các giá trị hợp lệ: {valid}"

    # Validate dates
    try:
        sd = date.fromisoformat(start_date)
    except ValueError:
        return f"❌ start_date không hợp lệ: '{start_date}'. Định dạng yêu cầu: YYYY-MM-DD"

    try:
        ed = date.fromisoformat(end_date)
    except ValueError:
        return f"❌ end_date không hợp lệ: '{end_date}'. Định dạng yêu cầu: YYYY-MM-DD"

    if ed < sd:
        return "❌ end_date phải sau hoặc bằng start_date"

    # Validate reason
    if not reason or not reason.strip():
        return "❌ Vui lòng cung cấp lý do nghỉ phép"

    num_days = (ed - sd).days + 1
    leave_label = LEAVE_LABELS[lt.value]

    extra_fields = {
        "leave_type":      lt.value,
        "leave_label":     leave_label,
        "start_date":      start_date,
        "end_date":        end_date,
        "num_days":        num_days,
        "reason":          reason,
        "handover_person": handover_person,
    }

    data = TicketCreate(
        ticket_type=TicketType.leave,
        title=f"Nghỉ phép — {leave_label} ({start_date} → {end_date})",
        description=reason,
        requester_name=requester_name,
        requester_email=requester_email,
        extra_fields=extra_fields,
    )
    ticket = await store.create(data)

    result = (
        f"✅ Đã tạo yêu cầu nghỉ phép {ticket.ticket_id}\n"
        f"Loại: {leave_label}\n"
        f"Từ: {sd.strftime('%d/%m/%Y')} đến {ed.strftime('%d/%m/%Y')} ({num_days} ngày)\n"
        f"Lý do: {reason}\n"
    )
    if handover_person:
        result += f"Người bàn giao: {handover_person}\n"
    result += "Trạng thái: Chờ phê duyệt"
    return result
