ANSWER_GENERATION_PROMPT = """Dựa trên ngữ cảnh nội quy công ty được cung cấp, hãy trả lời câu hỏi sau một cách chính xác và đầy đủ.

Câu hỏi: {question}

## Ngữ cảnh nội quy:
{context}

## Yêu cầu trả lời:
- Trả lời bằng tiếng Việt
- Trích dẫn chính sách/quy định cụ thể theo định dạng [Tên Chính sách, Điều X] hoặc [Tên tài liệu] khi có thể
- Nêu rõ đối tượng áp dụng (phòng ban nào, vai trò nào) nếu có sự khác biệt
- Nếu có ngoại lệ quan trọng, đề cập rõ ràng
- Nếu ngữ cảnh không đủ để trả lời, hãy nói rõ và hướng dẫn nhân viên liên hệ Phòng Nhân sự (hr@agentichouse.vn)
- Không bịa đặt thông tin ngoài ngữ cảnh đã cho
"""
