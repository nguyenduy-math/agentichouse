from app.claim_schema import FIELD_META
from app.health_profile_schema import PROFILE_FIELD_META
from app.schemas import ClaimData, ClaimType, HealthProfile

_ADVISOR_PERSONA = (
    "Bạn là trợ lý tư vấn bảo hiểm y tế chuyên nghiệp, thân thiện và kiên nhẫn. "
    "Bạn hỗ trợ người dùng Việt Nam khai thác quyền lợi bảo hiểm BHYT hoặc bảo hiểm thương mại. "
    "Luôn trả lời bằng tiếng Việt. Giữ giọng văn lịch sự, rõ ràng và ngắn gọn."
)

_EXTRACTION_SYSTEM = (
    "Bạn là bộ trích xuất thông tin bảo hiểm. "
    "Đọc tin nhắn của người dùng và trả về JSON chứa các trường thông tin bảo hiểm mà người dùng "
    "đã đề cập RÕ RÀNG. Với mọi trường không được đề cập, trả về null. "
    "Chuyển đổi ngày tháng sang định dạng YYYY-MM-DD nếu có thể. "
    "Chuyển đổi số tiền thành số nguyên (VNĐ). "
    "Với claim_type: 'outpatient' = ngoại trú/khám ngoại trú, "
    "'inpatient' = nội trú/nhập viện/nằm viện, 'private' = bảo hiểm thương mại/bảo hiểm nhân thọ."
)

_GUIDE_SYSTEM = (
    f"{_ADVISOR_PERSONA}\n\n"
    "Nhiệm vụ của bạn: dẫn dắt người dùng cung cấp từng thông tin cần thiết để hoàn thiện hồ sơ "
    "yêu cầu bồi thường. Chỉ hỏi MỘT câu hỏi mỗi lượt. "
    "Không hỏi lại thông tin đã được cung cấp. "
    "Hỏi tự nhiên như trong cuộc hội thoại thực, không liệt kê danh sách."
)

_PROPOSAL_SYSTEM = (
    f"{_ADVISOR_PERSONA}\n\n"
    "Dựa trên thông tin đã thu thập, hãy viết một đoạn tóm tắt hồ sơ yêu cầu bồi thường bảo hiểm "
    "bằng tiếng Việt, trình bày chuyên nghiệp và đầy đủ. "
    "Sau đó thông báo cho người dùng rằng hồ sơ đã sẵn sàng và họ có thể tải xuống."
)


def build_extraction_prompt(user_message: str) -> str:
    return user_message


def build_guide_prompt(
    collected: ClaimData,
    missing_fields: list[str],
    correction_field: str | None = None,
) -> str:
    collected_dict = collected.model_dump(exclude_none=True)
    collected_lines = []
    for field, value in collected_dict.items():
        meta = FIELD_META.get(field)
        label = meta.label_vi if meta else field
        collected_lines.append(f"  - {label}: {value}")

    missing_lines = []
    for field in missing_fields:
        meta = FIELD_META.get(field)
        if meta:
            missing_lines.append(f"  - {meta.label_vi} ({meta.hint})")

    collected_text = "\n".join(collected_lines) if collected_lines else "  (chưa có thông tin nào)"
    missing_text = "\n".join(missing_lines) if missing_lines else "  (không còn trường nào cần thu thập)"

    correction_note = ""
    if correction_field:
        meta = FIELD_META.get(correction_field)
        label = meta.label_vi if meta else correction_field
        value = collected_dict.get(correction_field, "")
        correction_note = (
            f"\nLƯU Ý: Người dùng vừa sửa trường '{label}' thành '{value}'. "
            "Hãy xác nhận việc cập nhật này trước, sau đó hỏi câu tiếp theo.\n"
        )

    return (
        f"Thông tin đã thu thập:\n{collected_text}\n\n"
        f"Thông tin còn thiếu:\n{missing_text}\n"
        f"{correction_note}\n"
        "Hãy hỏi câu tiếp theo để thu thập một trong các trường còn thiếu. "
        "Chọn trường quan trọng nhất hoặc logic nhất dựa trên ngữ cảnh."
    )


def build_confirmation_prompt(collected: ClaimData) -> str:
    lines = []
    for field, value in collected.model_dump(exclude_none=True).items():
        meta = FIELD_META.get(field)
        label = meta.label_vi if meta else field
        if isinstance(value, float):
            formatted = f"{value:,.0f} VNĐ"
        else:
            formatted = str(value)
        lines.append(f"  • {label}: {formatted}")

    info_text = "\n".join(lines)
    return (
        f"Đây là thông tin tôi đã thu thập được:\n\n{info_text}\n\n"
        "Thông tin trên có chính xác không? Bạn có thể:\n"
        "  1. Xác nhận để tôi tạo hồ sơ\n"
        "  2. Cho tôi biết thông tin nào cần sửa\n"
        "  3. Bắt đầu lại từ đầu"
    )


def build_document_continue_prompt(
    collected: ClaimData,
    missing_fields: list[str],
) -> str:
    """Prompt used right after document fields are merged: confirm what was read,
    then ask for the next missing field."""
    collected_dict = collected.model_dump(exclude_none=True)
    filled_lines = []
    for field, value in collected_dict.items():
        meta = FIELD_META.get(field)
        label = meta.label_vi if meta else field
        filled_lines.append(f"  - {label}: {value}")

    missing_lines = []
    for field in missing_fields:
        meta = FIELD_META.get(field)
        if meta:
            missing_lines.append(f"  - {meta.label_vi} ({meta.hint})")

    filled_text = "\n".join(filled_lines) if filled_lines else "  (không trích xuất được trường nào)"
    missing_text = "\n".join(missing_lines) if missing_lines else "  (không còn trường nào)"

    return (
        "Người dùng vừa tải lên một tài liệu. Hệ thống đã tự động trích xuất được các thông tin sau:\n"
        f"{filled_text}\n\n"
        f"Thông tin còn thiếu:\n{missing_text}\n\n"
        "Hãy xác nhận ngắn gọn với người dùng các thông tin đã đọc được từ tài liệu để họ kiểm tra, "
        "sau đó hỏi MỘT câu để thu thập trường còn thiếu quan trọng nhất. "
        "Tuyệt đối không hỏi lại các trường đã có ở trên."
    )


def build_proposal_prompt(collected: ClaimData) -> str:
    lines = []
    for field, value in collected.model_dump(exclude_none=True).items():
        meta = FIELD_META.get(field)
        label = meta.label_vi if meta else field
        lines.append(f"  - {label}: {value}")
    info_text = "\n".join(lines)
    return f"Thông tin hồ sơ:\n{info_text}\n\nViết tóm tắt hồ sơ và thông báo hoàn tất."


def get_extraction_system() -> str:
    return _EXTRACTION_SYSTEM


def get_guide_system() -> str:
    return _GUIDE_SYSTEM


def get_proposal_system() -> str:
    return _PROPOSAL_SYSTEM


# ---------------------------------------------------------------------------
# Recommendation flow prompts
# ---------------------------------------------------------------------------

_HEALTH_EXTRACTION_SYSTEM = (
    "Bạn là bộ trích xuất thông tin hồ sơ sức khỏe để tư vấn bảo hiểm. "
    "Đọc tin nhắn và trả về JSON chứa các trường mà người dùng đã đề cập RÕ RÀNG. "
    "Mọi trường không được đề cập trả về null. "
    "Quy tắc chuyển đổi:\n"
    "  - age: số tuổi nguyên (int)\n"
    "  - gender: 'nam' hoặc 'nữ'\n"
    "  - occupation_type: 'văn phòng', 'ngoài trời', hoặc 'lao động nặng'\n"
    "  - smoker: true nếu hút thuốc, false nếu không hút\n"
    "  - monthly_budget_vnd: số nguyên VNĐ\n"
    "  - num_insured: số nguyên (số người cần bảo hiểm)\n"
    "  - coverage_priority: chuỗi phân tách bằng dấu phẩy, VD: 'nội trú, bệnh hiểm nghèo'\n"
    "  - pre_existing_conditions: mô tả bệnh nền hoặc 'không' nếu không có"
)

_ADVISOR_GUIDE_SYSTEM = (
    "Bạn là chuyên gia tư vấn bảo hiểm sức khỏe, thân thiện và am hiểu thị trường Việt Nam. "
    "Nhiệm vụ: thu thập thông tin hồ sơ sức khỏe của người dùng để đề xuất gói bảo hiểm phù hợp. "
    "Chỉ hỏi MỘT câu mỗi lượt. Không hỏi lại điều đã biết. "
    "Hỏi tự nhiên, không liệt kê danh sách. Luôn trả lời bằng tiếng Việt."
)

_RECOMMENDATION_SYSTEM = (
    "Bạn là chuyên gia tư vấn bảo hiểm sức khỏe.\n\n"
    "QUAN TRỌNG: Bạn CHỈ được đề xuất các gói bảo hiểm có trong danh sách được cung cấp. "
    "TUYỆT ĐỐI không tự thêm gói, công ty, hoặc mức phí ngoài danh sách đó. "
    "Mọi thông tin (tên sản phẩm, công ty, mức phí, quyền lợi) phải lấy nguyên từ danh sách.\n\n"
    "Nhiệm vụ: Chọn 2-3 gói phù hợp nhất từ danh sách, giải thích tại sao phù hợp với hồ sơ "
    "khách hàng, và nêu rõ các điểm cần lưu ý một cách trung thực. "
    "Trả về JSON theo đúng schema được cung cấp. Luôn dùng tiếng Việt."
)


def build_profile_guide_prompt(
    profile: HealthProfile,
    missing_fields: list[str],
    correction_field: str | None = None,
) -> str:
    profile_dict = profile.model_dump(exclude_none=True)
    collected_lines = []
    for field, value in profile_dict.items():
        meta = PROFILE_FIELD_META.get(field)
        label = meta.label_vi if meta else field
        collected_lines.append(f"  - {label}: {value}")

    missing_lines = []
    for field in missing_fields:
        meta = PROFILE_FIELD_META.get(field)
        if meta:
            missing_lines.append(f"  - {meta.label_vi} ({meta.hint})")

    collected_text = "\n".join(collected_lines) if collected_lines else "  (chưa có thông tin nào)"
    missing_text = "\n".join(missing_lines) if missing_lines else "  (đã đủ thông tin)"

    correction_note = ""
    if correction_field:
        meta = PROFILE_FIELD_META.get(correction_field)
        label = meta.label_vi if meta else correction_field
        value = profile_dict.get(correction_field, "")
        correction_note = (
            f"\nLƯU Ý: Người dùng vừa cập nhật '{label}' thành '{value}'. "
            "Xác nhận trước, rồi hỏi tiếp.\n"
        )

    return (
        f"Thông tin đã thu thập:\n{collected_text}\n\n"
        f"Thông tin còn thiếu:\n{missing_text}\n"
        f"{correction_note}\n"
        "Hỏi câu tiếp theo để thu thập một trường còn thiếu."
    )


def build_profile_confirmation_prompt(profile: HealthProfile) -> str:
    lines = []
    for field, value in profile.model_dump(exclude_none=True).items():
        meta = PROFILE_FIELD_META.get(field)
        label = meta.label_vi if meta else field
        if isinstance(value, float):
            formatted = f"{value:,.0f} VNĐ/tháng"
        elif isinstance(value, bool):
            formatted = "Có" if value else "Không"
        else:
            formatted = str(value)
        lines.append(f"  • {label}: {formatted}")

    info_text = "\n".join(lines)
    return (
        f"Đây là hồ sơ tôi đã ghi nhận:\n\n{info_text}\n\n"
        "Thông tin trên có chính xác không?\n"
        "  1. Xác nhận — tôi sẽ đề xuất gói bảo hiểm phù hợp\n"
        "  2. Sửa thông tin\n"
        "  3. Bắt đầu lại từ đầu"
    )


def build_recommendation_prompt(profile: HealthProfile, catalog_text: str = "") -> str:
    lines = []
    for field, value in profile.model_dump(exclude_none=True).items():
        meta = PROFILE_FIELD_META.get(field)
        label = meta.label_vi if meta else field
        if isinstance(value, bool):
            formatted = "Có" if value else "Không"
        elif isinstance(value, float):
            formatted = f"{value:,.0f} VNĐ/tháng"
        else:
            formatted = str(value)
        lines.append(f"  - {label}: {formatted}")
    profile_text = "\n".join(lines)
    return (
        f"Hồ sơ khách hàng:\n{profile_text}\n\n"
        f"Danh sách gói bảo hiểm đủ điều kiện:\n{catalog_text}\n\n"
        "Chọn 2-3 gói phù hợp nhất từ danh sách trên và giải thích lý do. "
        "Chỉ được chọn từ danh sách này, không được thêm gói hoặc công ty nào khác."
    )


def get_health_extraction_system() -> str:
    return _HEALTH_EXTRACTION_SYSTEM


def get_advisor_guide_system() -> str:
    return _ADVISOR_GUIDE_SYSTEM


def get_recommendation_system() -> str:
    return _RECOMMENDATION_SYSTEM
