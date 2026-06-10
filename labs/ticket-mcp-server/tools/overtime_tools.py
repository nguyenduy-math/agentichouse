"""Overtime request tool with validation."""

from datetime import date as date_type
from typing import TYPE_CHECKING

from models.ticket import TicketCreate, TicketType

if TYPE_CHECKING:
    from storage.sqlite_store import SqliteStore

# Injected by server.py
store: "SqliteStore | None" = None

WEEKDAY_LABELS = {
    0: "Thứ Hai",
    1: "Thứ Ba",
    2: "Thứ Tư",
    3: "Thứ Năm",
    4: "Thứ Sáu",
    5: "Thứ Bảy",
    6: "Chủ nhật",
}


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

    Returns confirmation with ticket_id, date, hours, and status.
    """
    # Validate date
    try:
        ot_date = date_type.fromisoformat(date)
    except ValueError:
        return f"❌ date không hợp lệ: '{date}'. Định dạng yêu cầu: YYYY-MM-DD"

    # Validate hours
    if hours <= 0 or hours > 12:
        return "❌ Số giờ phải từ 0 đến 12 (không bao gồm 0)"

    # Validate reason
    if not reason or not reason.strip():
        return "❌ Vui lòng cung cấp lý do làm thêm giờ"

    weekday_label = WEEKDAY_LABELS[ot_date.weekday()]

    extra_fields = {
        "date":         date,
        "weekday":      weekday_label,
        "hours":        hours,
        "reason":       reason,
        "project_code": project_code,
    }

    data = TicketCreate(
        ticket_type=TicketType.overtime,
        title=f"Làm thêm giờ — {date} ({hours}h)",
        description=reason,
        requester_name=requester_name,
        requester_email=requester_email,
        extra_fields=extra_fields,
    )
    ticket = await store.create(data)

    result = (
        f"✅ Đã tạo yêu cầu làm thêm giờ {ticket.ticket_id}\n"
        f"Ngày: {ot_date.strftime('%d/%m/%Y')} ({weekday_label})\n"
        f"Số giờ: {hours} giờ\n"
        f"Lý do: {reason}\n"
    )
    if project_code:
        result += f"Dự án: {project_code}\n"
    result += "Trạng thái: Chờ phê duyệt"
    return result
