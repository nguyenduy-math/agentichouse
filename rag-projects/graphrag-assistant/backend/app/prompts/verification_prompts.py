from __future__ import annotations

ANSWER_VERIFICATION_PROMPT = """\
Bạn là chuyên gia kiểm tra chất lượng câu trả lời trong hệ thống hỏi đáp nội quy công ty.

## Câu hỏi của nhân viên:
{question}

## Ngữ cảnh nội quy được cung cấp cho hệ thống:
{context}

## Câu trả lời của hệ thống:
{answer}

Hãy đánh giá câu trả lời và trả về JSON với các trường sau:

- is_grounded (true/false): Mọi thông tin trong câu trả lời có được hỗ trợ bởi ngữ cảnh không?
  true = câu trả lời dựa hoàn toàn vào ngữ cảnh, không bịa đặt
  false = có thông tin bịa đặt, mâu thuẫn với ngữ cảnh, hoặc ngoài phạm vi tài liệu

- confidence (1-5): Mức độ tin cậy tổng thể
  5 = hoàn toàn chính xác và đầy đủ
  3 = một phần đúng hoặc thiếu chi tiết
  1 = sai hoặc không liên quan

- issues (danh sách chuỗi): Liệt kê các vấn đề cụ thể nếu có (rỗng nếu câu trả lời tốt)
"""

FALLBACK_ANSWER = (
    "Xin lỗi, tôi không tìm thấy thông tin đủ chính xác trong tài liệu nội quy để trả lời "
    "câu hỏi này. Vui lòng liên hệ bộ phận Nhân sự để được hỗ trợ thêm."
)
