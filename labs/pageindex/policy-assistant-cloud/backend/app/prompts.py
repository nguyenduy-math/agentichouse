"""Thư viện prompt tập trung — nơi duy nhất chứa mọi prompt gửi tới Gemini.

Tất cả prompt đều bằng tiếng Việt và tuân theo ``settings.response_language``.
Mỗi câu trả lời chia sẻ chung một cam kết "chỉ trả lời dựa trên tài liệu"
(GROUNDING_CLAUSE) và một quy ước trích dẫn (CITATION_GUIDANCE).

Khác với bản chạy PageIndex cục bộ: cây tri thức được xây trên PageIndex Cloud
rồi tải về dưới dạng JSON, nên bước điều hướng trả về ``node_id`` (định danh ổn
định của node trong cây) thay vì khoảng trang, và nội dung trả lời lấy trực tiếp
từ trường ``text`` của các node đã chọn.
"""

from __future__ import annotations

from app.config import settings


# ---------------------------------------------------------------------------
# Thông điệp dự phòng hướng tới người dùng
# ---------------------------------------------------------------------------

NO_DOCUMENTS_RESPONSE = (
    "Chưa có tài liệu nào được nạp. Vui lòng tải lên tài liệu chính sách "
    "(PDF) trước khi đặt câu hỏi."
)

NOT_FOUND_RESPONSE = (
    "Tôi không tìm thấy thông tin này trong các tài liệu chính sách hiện có. "
    "Vui lòng liên hệ phòng ban phụ trách để được hỗ trợ thêm."
)

DEFAULT_PAGEINDEX_PERSONA = "Bạn là chuyên gia tư vấn chính sách của công ty."


# ---------------------------------------------------------------------------
# Khối dùng chung: cam kết bám tài liệu + quy ước trích dẫn
# ---------------------------------------------------------------------------

GROUNDING_CLAUSE = (
    "Chỉ trả lời dựa trên nội dung tài liệu chính sách được cung cấp. "
    "Tuyệt đối không suy đoán hay bịa đặt thông tin. "
    "Nếu tài liệu không chứa câu trả lời, hãy nói rõ: "
    '"Tôi không tìm thấy thông tin này trong tài liệu chính sách" '
    "và hướng dẫn nhân viên liên hệ phòng ban phụ trách."
)

CITATION_GUIDANCE = (
    "Khi trích dẫn, ưu tiên định dạng [Tên tài liệu · Trang X] cho tài liệu có số trang, "
    "hoặc [Tên chính sách · Điều X] cho văn bản có điều khoản. "
    "Luôn giữ nguyên mọi trích dẫn trang/điều khoản có trong nguồn."
)


def _language_line() -> str:
    return f"Hãy trả lời bằng {settings.response_language}."


def compose_system_prompt(persona: str) -> str:
    """Persona + cam kết bám tài liệu + quy ước trích dẫn → một system prompt."""
    return "\n".join(
        part.strip()
        for part in (persona, GROUNDING_CLAUSE, CITATION_GUIDANCE, _language_line())
    )


def format_history(history: list[dict] | None, max_turns: int | None = None) -> str:
    """Render các lượt hội thoại gần đây thành một khối văn bản gọn.

    Trả về "" khi không có lịch sử để caller bỏ hẳn khối này.
    """
    if not history:
        return ""
    turns = history
    if max_turns is not None:
        turns = history[-max_turns * 2:]
    lines = []
    for msg in turns:
        who = "Nhân viên" if msg.get("role") != "assistant" else "Trợ lý"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{who}: {content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Điều hướng cây tri thức (trả về node_id)
# ---------------------------------------------------------------------------

_TREE_NAV_TEMPLATE = """\
Bạn đang điều hướng mục lục (cây phân cấp) của một tài liệu chính sách để tìm các mục liên quan đến câu hỏi của nhân viên.

Tài liệu: {document_name}
{history_block}\
Câu hỏi: {question}

Mục lục tài liệu (cây JSON gồm node_id, tiêu đề mục và tóm tắt):
{tree_json}

Nhiệm vụ:
1. Xác định các mục (node) liên quan nhất đến câu hỏi.
2. Trả về danh sách relevant_nodes, mỗi phần tử gồm node_id, title và lý do ngắn gọn (reason).
3. Chỉ dùng đúng các node_id xuất hiện trong cây ở trên.
4. Nếu không có mục nào liên quan, trả về danh sách rỗng.
"""


def build_tree_nav_prompt(
    document_name: str, question: str, tree_json: str, history_block: str = ""
) -> str:
    block = f"Bối cảnh hội thoại trước:\n{history_block}\n\n" if history_block else ""
    return _TREE_NAV_TEMPLATE.format(
        document_name=document_name,
        history_block=block,
        question=question,
        tree_json=tree_json,
    )


# ---------------------------------------------------------------------------
# Sinh câu trả lời có dẫn chứng (nội dung lấy từ text của các node đã chọn)
# ---------------------------------------------------------------------------

_ANSWER_TEMPLATE = """\
{persona}

{grounding}

Tài liệu: {document_name}
Các mục liên quan: {section_range}
{history_block}\
Nội dung trích từ tài liệu:
{content}

Câu hỏi: {question}

Trả lời chính xác và trích dẫn số trang/điều khoản. {language_line}
Đồng thời liệt kê các trang bạn thực sự dựa vào trong trường citations.
"""


def build_answer_prompt(
    persona: str,
    document_name: str,
    section_range: str,
    content: str,
    question: str,
    history_block: str = "",
) -> str:
    block = f"Bối cảnh hội thoại trước:\n{history_block}\n\n" if history_block else ""
    return _ANSWER_TEMPLATE.format(
        persona=persona.strip(),
        grounding=GROUNDING_CLAUSE,
        document_name=document_name,
        section_range=section_range,
        history_block=block,
        content=content,
        question=question,
        language_line=_language_line(),
    )


# ---------------------------------------------------------------------------
# Tổng hợp câu trả lời từ nhiều tài liệu
# ---------------------------------------------------------------------------

_SYNTHESIS_TEMPLATE = """\
Bạn đang tổng hợp thông tin từ {n} tài liệu chính sách để trả lời câu hỏi của nhân viên.

Các câu trả lời (kèm trích dẫn) từ từng tài liệu:
{answers_block}

Câu hỏi của nhân viên: {question}

Hãy tạo một câu trả lời rõ ràng, mạch lạc, giữ nguyên mọi trích dẫn trang/điều khoản.
Nếu các tài liệu mâu thuẫn nhau, hãy nêu rõ sự khác biệt.
Nếu không tài liệu nào chứa câu trả lời, hãy nói rõ. {language_line}
"""


def build_synthesis_prompt(n: int, answers_block: str, question: str) -> str:
    return _SYNTHESIS_TEMPLATE.format(
        n=n,
        answers_block=answers_block,
        question=question,
        language_line=_language_line(),
    )
