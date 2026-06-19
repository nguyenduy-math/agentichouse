ENTITY_EXTRACTION_PROMPT = """Bạn là chuyên gia phân tích tài liệu nội quy và chính sách công ty.
Từ đoạn văn bản sau, hãy trích xuất:

1. CÁC THỰC THỂ (entities): các đối tượng quan trọng trong nội quy công ty
2. CÁC QUAN HỆ (relations) giữa các thực thể với các loại:
   - AP_DUNG_CHO: chính sách/quy tắc áp dụng cho phòng ban hoặc vai trò nào
   - MIEN_TRU: ngoại lệ miễn trừ khỏi một quy tắc
   - GHI_DE: chính sách mới thay thế chính sách cũ
   - THAM_CHIEU: chính sách này tham chiếu đến chính sách khác
   - YEU_CAU: quy tắc yêu cầu thực hiện một quy trình
   - CUNG_CAP: vai trò/phòng ban được hưởng một quyền lợi
   - THUC_THI_BOI: quy tắc được thực thi bởi phòng ban nào

Các loại thực thể được phép:
- CHINH_SACH: chính sách cấp cao (Chính sách trang phục, Chính sách nghỉ phép...)
- QUY_TAC: quy tắc cụ thể trong chính sách (Business casual thứ Hai–Năm, Nghỉ ốm 10 ngày/năm...)
- PHONG_BAN: bộ phận/phòng ban (Phòng Kỹ thuật, Phòng Kinh doanh, Ban Giám đốc...)
- VAI_TRO: vai trò/chức danh (Nhân viên Junior, Trưởng phòng, Thực tập sinh, Nhà thầu...)
- QUY_TRINH: quy trình thực hiện (Quy trình xin phép, Quy trình onboarding...)
- QUYEN_LOI: phúc lợi, trợ cấp (Phụ cấp ăn trưa, Bảo hiểm sức khỏe PTI, Thưởng cuối năm...)
- NGOAI_LE: trường hợp ngoại lệ (Ngoại lệ y tế, Casual Friday, Ngày tiếp khách...)

Văn bản:
{chunk_text}

Trả về JSON hợp lệ theo schema sau (không có text nào ngoài JSON):
{{
  "entities": [
    {{"name": "...", "type": "CHINH_SACH|QUY_TAC|PHONG_BAN|VAI_TRO|QUY_TRINH|QUYEN_LOI|NGOAI_LE", "description": "..."}}
  ],
  "relations": [
    {{"source": "entity_name", "target": "entity_name", "relation": "RELATION_TYPE"}}
  ]
}}
"""

COMMUNITY_SUMMARY_PROMPT = """Dưới đây là danh sách các thực thể thuộc cùng một nhóm chủ đề (community) trong đồ thị tri thức nội quy công ty:

Thực thể:
{nodes_text}

Quan hệ:
{edges_text}

Hãy viết một đoạn tóm tắt ngắn (3–5 câu) bằng tiếng Việt về chủ đề nội quy mà nhóm này bao phủ. Tóm tắt phải:
- Nêu rõ lĩnh vực nội quy chính (ví dụ: trang phục, nghỉ phép, phúc lợi, làm việc từ xa...)
- Liệt kê các chính sách và quy tắc chính trong nhóm
- Mô tả đối tượng áp dụng (phòng ban, vai trò nào)
- Viết ngắn gọn, dễ hiểu cho nhân viên mới
"""

QUERY_CLASSIFICATION_PROMPT = """Phân loại câu hỏi về nội quy công ty sau thành một trong hai loại:
- LOCAL: câu hỏi về quy định cụ thể, con số cụ thể, điều kiện cụ thể, quy trình cụ thể, phòng ban cụ thể
- GLOBAL: câu hỏi tổng quan, tóm tắt toàn bộ chủ đề, so sánh nhiều chính sách, hỏi về chủ đề rộng

Câu hỏi: "{question}"

Trả về JSON hợp lệ (không có text nào ngoài JSON):
{{"query_type": "LOCAL"}} hoặc {{"query_type": "GLOBAL"}}
"""
