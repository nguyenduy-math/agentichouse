"""
Single source of truth for domain configuration.
Add new domains here; the orchestrator and agent registry pick them up automatically.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Domain:
    key: str             # used in orchestrator classification output
    name_vi: str         # Vietnamese display name
    description_vi: str  # used in orchestrator's classification prompt


DOMAINS: list[Domain] = [
    Domain(
        key="hr",
        name_vi="Nhân sự",
        description_vi="Chính sách tuyển dụng, hợp đồng lao động, kỷ luật, nghỉ phép, đánh giá hiệu suất",
    ),
    Domain(
        key="benefits",
        name_vi="Phúc lợi",
        description_vi="Bảo hiểm y tế, bảo hiểm xã hội, phụ cấp, chế độ nghỉ thai sản, quỹ hưu trí",
    ),
    Domain(
        key="it",
        name_vi="Bảo mật CNTT",
        description_vi="Chính sách an toàn thông tin, quy trình bảo mật, quản lý mật khẩu, quyền truy cập hệ thống",
    ),
    Domain(
        key="finance",
        name_vi="Tài chính",
        description_vi="Quy trình thanh toán, hoàn chi phí, ngân sách, báo cáo tài chính, kiểm soát nội bộ",
    ),
    Domain(
        key="compliance",
        name_vi="Tuân thủ",
        description_vi="Quy định pháp luật, tiêu chuẩn ngành, báo cáo kiểm toán, phòng chống tham nhũng",
    ),
    Domain(
        key="procedures",
        name_vi="Quy trình",
        description_vi="Quy trình vận hành chuẩn (SOP), hướng dẫn công việc, biểu mẫu, phê duyệt nội bộ",
    ),
    Domain(
        key="general",
        name_vi="Tổng hợp",
        description_vi="Câu hỏi chung không thuộc các lĩnh vực chuyên biệt trên",
    ),
]

DOMAIN_MAP: dict[str, Domain] = {d.key: d for d in DOMAINS}
