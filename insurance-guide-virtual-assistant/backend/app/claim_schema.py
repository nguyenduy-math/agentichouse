from dataclasses import dataclass

from app.schemas import ClaimType


@dataclass(frozen=True)
class FieldMeta:
    label_vi: str
    hint: str


FIELD_META: dict[str, FieldMeta] = {
    "claim_type":     FieldMeta("Loại hình bảo hiểm", "ngoại trú / nội trú / bảo hiểm thương mại"),
    "name":           FieldMeta("Họ và tên", "VD: Nguyễn Văn A"),
    "dob":            FieldMeta("Ngày sinh", "VD: 15/03/1990"),
    "insurance_id":   FieldMeta("Mã số BHXH", "10 chữ số trên thẻ BHYT"),
    "policy_number":  FieldMeta("Số hợp đồng bảo hiểm", "Trên thẻ/hợp đồng bảo hiểm thương mại"),
    "hospital":       FieldMeta("Cơ sở khám chữa bệnh", "VD: Bệnh viện Bạch Mai"),
    "visit_date":     FieldMeta("Ngày khám", "VD: 20/05/2025"),
    "admission_date": FieldMeta("Ngày nhập viện", "VD: 10/05/2025"),
    "discharge_date": FieldMeta("Ngày xuất viện", "VD: 15/05/2025"),
    "event_date":     FieldMeta("Ngày xảy ra sự kiện", "VD: 20/05/2025"),
    "diagnosis":      FieldMeta("Chẩn đoán bệnh", "VD: Viêm phổi, gãy xương tay"),
    "diagnosis_code": FieldMeta("Mã ICD-10", "VD: J18.9 (không bắt buộc)"),
    "total_cost":     FieldMeta("Tổng chi phí điều trị (VNĐ)", "VD: 5.000.000"),
    "patient_paid":   FieldMeta("Số tiền bệnh nhân tự trả (VNĐ)", "Phần không được BHYT chi trả"),
    "bank_account":   FieldMeta("Số tài khoản ngân hàng", "Để nhận hoàn tiền bảo hiểm thương mại"),
    "notes":          FieldMeta("Ghi chú thêm", "Thông tin bổ sung nếu có"),
}

REQUIRED_FIELDS: dict[ClaimType, list[str]] = {
    ClaimType.outpatient: [
        "name", "dob", "insurance_id", "hospital",
        "visit_date", "diagnosis", "total_cost",
    ],
    ClaimType.inpatient: [
        "name", "dob", "insurance_id", "hospital",
        "admission_date", "discharge_date", "diagnosis",
        "total_cost", "patient_paid",
    ],
    ClaimType.private: [
        "name", "dob", "policy_number", "hospital",
        "event_date", "diagnosis", "total_cost", "bank_account",
    ],
    ClaimType.unknown: [],
}


def get_missing_fields(collected_dict: dict, claim_type: ClaimType) -> list[str]:
    required = REQUIRED_FIELDS.get(claim_type, [])
    return [f for f in required if not collected_dict.get(f)]


def compute_progress(collected_dict: dict, claim_type: ClaimType) -> int:
    required = REQUIRED_FIELDS.get(claim_type, [])
    if not required:
        return 0
    filled = sum(1 for f in required if collected_dict.get(f))
    return round(filled * 100 / len(required))
