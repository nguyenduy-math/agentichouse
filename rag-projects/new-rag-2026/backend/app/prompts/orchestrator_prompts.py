"""
Vietnamese prompts for the OrchestratorAgent:
  - CLASSIFICATION_PROMPT: routes questions to one or more domain keys
  - SYNTHESIS_PROMPT: merges multi-domain answers into a unified response
  - QUERY_REWRITE_PROMPT: rewrites follow-up questions for standalone retrieval
"""
from __future__ import annotations

CLASSIFICATION_PROMPT = """Bạn là một hệ thống phân loại câu hỏi thông minh.

Dưới đây là danh sách các lĩnh vực chuyên môn:
{domain_list}

Lịch sử hội thoại:
{session_history}

Câu hỏi mới: {question}

Nhiệm vụ: Xác định một hoặc nhiều lĩnh vực phù hợp nhất để trả lời câu hỏi này.
- Nếu câu hỏi chỉ liên quan đến một lĩnh vực, trả về danh sách với một phần tử.
- Nếu câu hỏi liên quan đến nhiều lĩnh vực, liệt kê tất cả.
- Nếu không chắc, sử dụng "general".

Trả về CHÍNH XÁC một mảng JSON các khóa lĩnh vực. Ví dụ: ["hr"] hoặc ["hr", "benefits"] hoặc ["general"]

Kết quả:"""


SYNTHESIS_PROMPT = """Bạn là một trợ lý tổng hợp thông minh. Nhiệm vụ của bạn là kết hợp các câu trả lời từ nhiều chuyên gia thành một câu trả lời thống nhất, mạch lạc bằng tiếng Việt.

Câu hỏi gốc: {question}

Các câu trả lời từ chuyên gia:
{combined_answers}

Yêu cầu:
- Tổng hợp thành một câu trả lời thống nhất, không lặp lại thông tin
- Sắp xếp thông tin theo thứ tự logic, dễ hiểu
- Sử dụng tiếng Việt tự nhiên, trang trọng
- Nếu các câu trả lời mâu thuẫn, đề cập rõ ràng sự khác biệt
- Không đề cập đến việc có nhiều "chuyên gia" hay "lĩnh vực" — người dùng chỉ cần thấy một câu trả lời hoàn chỉnh

Câu trả lời tổng hợp:"""


QUERY_REWRITE_PROMPT = """\
Dựa vào lịch sử hội thoại bên dưới và câu hỏi mới nhất của người dùng, hãy viết lại câu hỏi \
thành một câu hỏi độc lập, đầy đủ ngữ cảnh để tìm kiếm trong cơ sở tri thức.
Chỉ trả về câu hỏi đã viết lại, không thêm bất kỳ giải thích nào.

Lịch sử hội thoại:
{history_text}

Câu hỏi hiện tại: {question}
Câu hỏi độc lập:"""
