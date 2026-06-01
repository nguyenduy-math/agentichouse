import json
import uuid
from datetime import datetime

_tickets: dict = {}
_notifications: list = []
_escalations: list = []
_feedbacks: list = []


def register_utility_tools(mcp):
    @mcp.tool()
    def create_support_ticket(customer_id: str, issue: str, priority: str = "normal") -> str:
        """Tạo phiếu hỗ trợ kỹ thuật mới. priority: low | normal | high | urgent"""
        ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
        ticket = {
            "id": ticket_id,
            "customer_id": customer_id,
            "issue": issue[:300],
            "priority": priority,
            "status": "Đang chờ xử lý",
            "created_at": datetime.now().isoformat(),
        }
        _tickets[ticket_id] = ticket
        return json.dumps({"success": True, "ticket": ticket}, ensure_ascii=False)

    @mcp.tool()
    def send_notification(customer_id: str, message: str, channel: str = "email") -> str:
        """Gửi thông báo cho khách hàng. channel: email | sms"""
        notif = {
            "id": str(uuid.uuid4())[:8],
            "customer_id": customer_id,
            "message": message,
            "channel": channel,
            "sent_at": datetime.now().isoformat(),
            "status": "đã gửi",
        }
        _notifications.append(notif)
        return json.dumps({"success": True, "notification": notif}, ensure_ascii=False)

    @mcp.tool()
    def escalate_to_human(customer_id: str, reason: str, urgency: str = "normal") -> str:
        """Chuyển tiếp cuộc hội thoại đến nhân viên hỗ trợ. urgency: low | normal | high"""
        escalation = {
            "id": f"ESC-{str(uuid.uuid4())[:8].upper()}",
            "customer_id": customer_id,
            "reason": reason[:200],
            "urgency": urgency,
            "status": "Đang chờ nhân viên tiếp nhận",
            "estimated_wait": "5-10 phút",
            "created_at": datetime.now().isoformat(),
        }
        _escalations.append(escalation)
        return json.dumps({"success": True, "escalation": escalation}, ensure_ascii=False)

    @mcp.tool()
    def log_feedback(customer_id: str, rating: int, comment: str = "") -> str:
        """Ghi nhận đánh giá và phản hồi từ khách hàng. rating: 1-5"""
        feedback = {
            "id": str(uuid.uuid4())[:8],
            "customer_id": customer_id,
            "rating": max(1, min(5, rating)),
            "comment": comment,
            "created_at": datetime.now().isoformat(),
        }
        _feedbacks.append(feedback)
        return json.dumps({"success": True, "feedback": feedback}, ensure_ascii=False)
