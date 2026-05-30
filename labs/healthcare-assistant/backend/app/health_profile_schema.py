from dataclasses import dataclass

from app.schemas import HealthProfile


@dataclass(frozen=True)
class FieldMeta:
    label_vi: str
    hint: str


PROFILE_FIELD_META: dict[str, FieldMeta] = {
    "age":                    FieldMeta("Tuổi", "VD: 30"),
    "gender":                 FieldMeta("Giới tính", "nam / nữ"),
    "occupation_type":        FieldMeta("Loại công việc", "văn phòng / ngoài trời / lao động nặng"),
    "pre_existing_conditions":FieldMeta("Bệnh nền", "VD: tiểu đường, huyết áp cao, hoặc 'không'"),
    "smoker":                 FieldMeta("Có hút thuốc không", "có / không"),
    "monthly_budget_vnd":     FieldMeta("Ngân sách hàng tháng (VNĐ)", "VD: 1.000.000"),
    "num_insured":            FieldMeta("Số người cần bảo hiểm", "VD: 1, 2, hoặc cả gia đình"),
    "coverage_priority":      FieldMeta("Ưu tiên quyền lợi", "Nội trú / Ngoại trú / Bệnh hiểm nghèo / Tai nạn / Nhân thọ"),
}

REQUIRED_PROFILE_FIELDS: list[str] = [
    "age",
    "gender",
    "occupation_type",
    "smoker",
    "monthly_budget_vnd",
    "num_insured",
    "coverage_priority",
]

# Fields that trigger specific option chips when the agent asks about them
FIELD_CHIPS: dict[str, list[str]] = {
    "gender":           ["Nam", "Nữ"],
    "smoker":           ["Có hút thuốc", "Không hút thuốc"],
    "occupation_type":  ["Văn phòng", "Ngoài trời / di chuyển nhiều", "Lao động nặng"],
    "coverage_priority":["Nội trú", "Ngoại trú", "Bệnh hiểm nghèo", "Tai nạn", "Bảo hiểm nhân thọ"],
}


def get_missing_profile_fields(profile: HealthProfile) -> list[str]:
    profile_dict = profile.model_dump()
    return [f for f in REQUIRED_PROFILE_FIELDS if profile_dict.get(f) is None]


def compute_profile_progress(profile: HealthProfile) -> int:
    profile_dict = profile.model_dump()
    filled = sum(1 for f in REQUIRED_PROFILE_FIELDS if profile_dict.get(f) is not None)
    return round(filled * 100 / len(REQUIRED_PROFILE_FIELDS))


def get_field_chips(field: str) -> list[str] | None:
    return FIELD_CHIPS.get(field)
