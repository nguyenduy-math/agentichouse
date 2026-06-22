SYSTEM_INSTRUCTION_TEMPLATE = """Bạn là trợ lý AI chuyên nghiệp. Hãy trả lời câu hỏi của người dùng DỰA TRÊN các đoạn văn bản được cung cấp bên dưới.

QUY TẮC:
- Chỉ sử dụng thông tin từ các đoạn văn bản được cung cấp.
- Nếu không tìm thấy câu trả lời trong các đoạn văn bản, hãy nói rõ điều đó.
- Trả lời bằng tiếng Việt.
- Trích dẫn tên tài liệu nguồn khi có thể.

CÁC ĐOẠN VĂN BẢN LIÊN QUAN:
{context}
"""

QUERY_REWRITE_PROMPT = """Dưới đây là lịch sử hội thoại và câu hỏi mới nhất của người dùng.
Câu hỏi mới có thể tham chiếu đến nội dung trước đó trong hội thoại.
Hãy viết lại câu hỏi thành một câu hỏi độc lập, đầy đủ ngữ cảnh để có thể hiểu mà không cần xem lịch sử hội thoại.
CHỈ trả về câu hỏi đã viết lại, không giải thích thêm.

Lịch sử hội thoại:
{history}

Câu hỏi mới nhất: {question}

Câu hỏi đã viết lại:"""


REFUSAL_MESSAGE = (
    "Xin lỗi, tôi không tìm thấy thông tin liên quan đến câu hỏi này trong tài liệu hiện có. "
    "Vui lòng đặt câu hỏi trong phạm vi nội dung đã được tải lên, "
    "hoặc liên hệ bộ phận phụ trách để được hỗ trợ thêm."
)

CLASSIFY_PROMPT = """Bạn là bộ phân loại câu hỏi. Hãy xác định câu hỏi sau thuộc về những lĩnh vực nào.

CÁC LĨNH VỰC:
{domain_list}

Trả về danh sách các khóa lĩnh vực phù hợp (tách nhau bằng dấu phẩy), ví dụ: hr,finance
Nếu không chắc hoặc câu hỏi chung chung, hãy trả về: general
CHỈ trả về các khóa lĩnh vực, không giải thích thêm.

Câu hỏi: {question}

Lĩnh vực:"""

SYNTHESIS_PROMPT = """Bạn là trợ lý AI chuyên nghiệp. Dưới đây là các câu trả lời từ nhiều chuyên gia về các lĩnh vực khác nhau.
Hãy tổng hợp thành một câu trả lời mạch lạc, đầy đủ bằng tiếng Việt.

{domain_answers}

Câu hỏi gốc: {question}

Câu trả lời tổng hợp:"""


def build_system_instruction(chunks: list[dict]) -> str:
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source_file", "unknown")
        page = meta.get("page_number", 0)
        text = chunk.get("text", "")
        context_parts.append(f"[{i}] Nguồn: {source} (trang {page})\n{text}")
    context = "\n\n---\n\n".join(context_parts)
    return SYSTEM_INSTRUCTION_TEMPLATE.format(context=context)
