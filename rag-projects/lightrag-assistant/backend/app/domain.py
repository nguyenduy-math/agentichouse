"""Vietnam-insurance domain tuning: entity types + the domain answer prompt.

Kept in one small module so the domain behaviour is easy to find and adjust.
"""

from __future__ import annotations

# Entity types LightRAG should extract from Vietnamese insurance documents.
# Fed into LightRAG's addon_params["entity_types"] at construction time.
INSURANCE_ENTITY_TYPES: list[str] = [
    "insurance_product",   # sản phẩm bảo hiểm
    "insurer",             # doanh nghiệp bảo hiểm
    "policyholder",        # bên mua bảo hiểm
    "insured_person",      # người được bảo hiểm
    "beneficiary",         # người thụ hưởng
    "coverage",            # phạm vi bảo hiểm
    "benefit",             # quyền lợi chi trả
    "exclusion",           # điểm loại trừ
    "premium",             # phí bảo hiểm
    "sum_insured",         # số tiền bảo hiểm
    "claim_process",       # quy trình bồi thường
    "waiting_period",      # thời gian chờ
    "term_condition",      # điều khoản, điều kiện hợp đồng
    "regulation",          # quy định pháp luật (thông tư, nghị định, luật)
    "organization",
    "date",
]

# Passed as QueryParam.user_prompt — shapes how the assistant phrases answers.
DOMAIN_USER_PROMPT: str = """\
Bạn là trợ lý chuyên gia về bảo hiểm tại Việt Nam. Hãy tuân thủ các nguyên tắc sau:

1. Chỉ trả lời dựa trên thông tin có trong ngữ cảnh được cung cấp. Tuyệt đối không bịa đặt.
2. Nếu thông tin không có trong tài liệu, hãy nói rõ:
   "Thông tin này không có trong tài liệu hiện có."
3. Khi trích dẫn, nêu rõ tên tài liệu và điều khoản/mục liên quan (ví dụ: "theo Điều 5...").
4. Trả lời bằng tiếng Việt, chính xác về các thuật ngữ bảo hiểm: phạm vi bảo hiểm, quyền lợi,
   điểm loại trừ, phí bảo hiểm, thời gian chờ, quy trình bồi thường, số tiền bảo hiểm.
5. Kết thúc câu trả lời bằng đúng một dòng lưu ý:
   "Lưu ý: Thông tin chỉ mang tính tham khảo, không thay thế tư vấn pháp lý hoặc tài chính chính thức."
"""
