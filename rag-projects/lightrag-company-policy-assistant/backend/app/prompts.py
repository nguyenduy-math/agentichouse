"""Centralized prompt library — the single place every LLM prompt lives.

Before this module, prompts were scattered across the orchestrator, the PageIndex
service, and each agent file, with drifting styles and even drifting output
languages (some Vietnamese, some English). Centralizing them makes prompts
reviewable and diffable as one unit, and lets every agent share one grounding
contract and one citation convention.

Conventions enforced here:
  * Output language is driven by ``settings.response_language`` (audit ref: A2).
  * Every agent system prompt = persona + shared GROUNDING_CLAUSE + CITATION_GUIDANCE
    (audit refs: A3, A4).
  * The classifier prompt is built from ``domains.domain_lines()`` so it can never
    drift from the real domain set, and it carries few-shot examples (audit ref: A5).

Prompt changelog:
  v1 (2026-05-20) — initial extraction + few-shot classifier, shared grounding/citation,
                    language-driven synthesis & answer prompts.
"""

from __future__ import annotations

from app.config import settings
from app.domains import domain_lines


# ---------------------------------------------------------------------------
# Shared building blocks (A3 grounding, A4 citation style)
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
    """Persona + shared grounding + citation contract → one agent system prompt."""
    return "\n".join(
        part.strip() for part in (persona, GROUNDING_CLAUSE, CITATION_GUIDANCE, _language_line())
    )


def format_history(history: list[dict] | None, max_turns: int | None = None) -> str:
    """Render recent turns as a compact block for prompts that take plain text.

    Returns "" when there is no history, so callers can drop the block entirely.
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
# Orchestrator: classification (A5) + synthesis (A2)
# ---------------------------------------------------------------------------

_CLASSIFY_TEMPLATE = """\
Phân loại câu hỏi của nhân viên vào một hoặc nhiều lĩnh vực chính sách của công ty.

Các lĩnh vực:
{domain_catalogue}

{history_block}\
Câu hỏi hiện tại: "{question}"

Quy tắc:
- Trả về 1 đến 3 lĩnh vực liên quan nhất, theo thứ tự ưu tiên (liên quan nhất trước).
- Chỉ dùng đúng các mã lĩnh vực ở trên.
- Nếu câu hỏi là lời chào, cảm ơn hoặc hoàn toàn không liên quan đến chính sách, trả về danh sách rỗng.
- Nếu câu hỏi là câu hỏi nối tiếp (ví dụ "thế còn nhà thầu thì sao?"), dựa vào lịch sử để xác định lĩnh vực.

Ví dụ:
- "Tôi được nghỉ phép năm bao nhiêu ngày?" → {{"domains": ["BENEFITS"]}}
- "Các bước nộp đề xuất hoàn ứng là gì?" → {{"domains": ["PROCEDURES", "FINANCE"]}}
- "Nhân viên bán thời gian có bảo hiểm y tế và mấy ngày nghỉ ốm?" → {{"domains": ["BENEFITS", "MEDICAL", "HR_POLICY"]}}
- "Cảm ơn bạn nhé!" → {{"domains": []}}
"""


def build_classification_prompt(question: str, history_block: str = "") -> str:
    block = f"Lịch sử hội thoại gần đây:\n{history_block}\n\n" if history_block else ""
    return _CLASSIFY_TEMPLATE.format(
        domain_catalogue=domain_lines(),
        history_block=block,
        question=question,
    )


_SYNTHESIZE_TEMPLATE = """\
Bạn đang tổng hợp câu trả lời từ nhiều chuyên gia tư vấn chính sách công ty để trả lời một câu hỏi của nhân viên.

Câu hỏi của nhân viên: {question}

Câu trả lời từ các chuyên gia:
{answers_block}

Hướng dẫn:
- Kết hợp thành một câu trả lời mạch lạc, ngắn gọn, chính xác.
- Giữ nguyên TẤT CẢ trích dẫn trang/điều khoản từ các câu trả lời gốc.
- Nếu các chuyên gia mâu thuẫn nhau, hãy nêu rõ sự khác biệt.
- Không thêm thông tin ngoài những gì các chuyên gia đã cung cấp.
- {language_line}

Câu trả lời tổng hợp:
"""


def build_synthesis_prompt(question: str, answers_block: str) -> str:
    return _SYNTHESIZE_TEMPLATE.format(
        question=question,
        answers_block=answers_block,
        language_line=_language_line(),
    )


# ---------------------------------------------------------------------------
# PageIndex: tree navigation + grounded answer + per-domain synthesis (A2, A3, B4, D1, D3)
# ---------------------------------------------------------------------------

_TREE_NAV_TEMPLATE = """\
Bạn đang điều hướng mục lục (cây phân cấp) của một tài liệu chính sách để tìm phần liên quan đến câu hỏi của nhân viên.

Tài liệu: {document_name}
{history_block}\
Câu hỏi: {question}

Mục lục tài liệu (cây JSON gồm tiêu đề mục, tóm tắt, khoảng trang):
{tree_json}

Nhiệm vụ:
1. Xác định các mục liên quan nhất đến câu hỏi.
2. Trả về node_id và khoảng trang của các mục cần đọc.
3. Nếu không có mục nào liên quan, trả về danh sách rỗng.
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


_ANSWER_TEMPLATE = """\
{persona}

{grounding}

Tài liệu: {document_name}
Trang liên quan: {page_range}
{history_block}\
Nội dung trích từ tài liệu:
{content}

Câu hỏi: {question}

Trả lời chính xác và trích dẫn số trang. {language_line}
Đồng thời liệt kê các trang bạn thực sự dựa vào trong trường citations.
"""


def build_answer_prompt(
    persona: str,
    document_name: str,
    page_range: str,
    content: str,
    question: str,
    history_block: str = "",
) -> str:
    block = f"Bối cảnh hội thoại trước:\n{history_block}\n\n" if history_block else ""
    return _ANSWER_TEMPLATE.format(
        persona=persona.strip(),
        grounding=GROUNDING_CLAUSE,
        document_name=document_name,
        page_range=page_range,
        history_block=block,
        content=content,
        question=question,
        language_line=_language_line(),
    )


_PI_SYNTHESIS_TEMPLATE = """\
Bạn đang tổng hợp thông tin từ {n} tài liệu chính sách để trả lời câu hỏi của nhân viên.

Các câu trả lời (kèm trích dẫn trang) từ từng tài liệu:
{answers_block}

Câu hỏi của nhân viên: {question}

Hãy tạo một câu trả lời rõ ràng, giữ nguyên mọi trích dẫn trang. Nếu các tài liệu mâu thuẫn, nêu rõ.
Nếu không tài liệu nào chứa câu trả lời, hãy nói rõ. {language_line}
"""


def build_pageindex_synthesis_prompt(n: int, answers_block: str, question: str) -> str:
    return _PI_SYNTHESIS_TEMPLATE.format(
        n=n,
        answers_block=answers_block,
        question=question,
        language_line=_language_line(),
    )
