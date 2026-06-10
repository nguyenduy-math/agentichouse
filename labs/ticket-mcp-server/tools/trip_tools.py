"""Business trip request tool with validation."""

from datetime import date
from typing import TYPE_CHECKING

from models.ticket import TicketCreate, TicketType

if TYPE_CHECKING:
    from storage.sqlite_store import SqliteStore

# Injected by server.py
store: "SqliteStore | None" = None

VALID_TRANSPORT_MODES = {"plane", "train", "car", "other", ""}

TRANSPORT_LABELS: dict[str, str] = {
    "plane": "Máy bay",
    "train": "Tàu hỏa",
    "car":   "Ô tô",
    "other": "Khác",
    "":      "",
}


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

    Returns confirmation with ticket_id, destination, dates, duration, and status.
    """
    # Validate required strings
    if not destination or not destination.strip():
        return "❌ Vui lòng cung cấp điểm đến (destination)"

    if not purpose or not purpose.strip():
        return "❌ Vui lòng cung cấp mục đích công tác (purpose)"

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

    # Validate budget
    if estimated_budget_vnd < 0:
        return "❌ Ngân sách dự kiến phải >= 0"

    # Validate transport mode
    if transport_mode not in VALID_TRANSPORT_MODES:
        return f"❌ Phương tiện không hợp lệ: '{transport_mode}'. Các giá trị hợp lệ: plane | train | car | other"

    num_days = (ed - sd).days + 1

    extra_fields = {
        "destination":          destination,
        "purpose":              purpose,
        "start_date":           start_date,
        "end_date":             end_date,
        "num_days":             num_days,
        "estimated_budget_vnd": estimated_budget_vnd,
        "transport_mode":       transport_mode,
    }

    data = TicketCreate(
        ticket_type=TicketType.trip,
        title=f"Công tác — {destination} ({start_date} → {end_date})",
        description=purpose,
        requester_name=requester_name,
        requester_email=requester_email,
        extra_fields=extra_fields,
    )
    ticket = await store.create(data)

    result = (
        f"✅ Đã tạo yêu cầu công tác {ticket.ticket_id}\n"
        f"Điểm đến: {destination}\n"
        f"Mục đích: {purpose}\n"
        f"Từ: {sd.strftime('%d/%m/%Y')} đến {ed.strftime('%d/%m/%Y')} ({num_days} ngày)\n"
    )
    if estimated_budget_vnd > 0:
        result += f"Ngân sách dự kiến: {estimated_budget_vnd:,} VND\n"
    if transport_mode:
        result += f"Phương tiện: {TRANSPORT_LABELS.get(transport_mode, transport_mode)}\n"
    result += "Trạng thái: Chờ phê duyệt"
    return result
