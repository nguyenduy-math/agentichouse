"""Single source of truth for the policy domains.

Every place that needs the list of domains — the API schema (``schemas.DomainKey``),
the orchestrator's ``ALL_DOMAINS``, the classifier prompt, and the ingest
``doc_type → domain`` map — derives from the ``DOMAINS`` registry below. Adding a
new domain means editing this file (and registering an agent in ``main.py``);
nothing else needs to change.

Audit refs: B1 (stale DomainKey — was 5 of 10 domains).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args


@dataclass(frozen=True)
class DomainInfo:
    """Metadata for one policy domain."""

    key: str          # canonical domain key (e.g. "HR_POLICY")
    doc_type: str     # data/documents/<doc_type>/ sub-folder name
    engine: str       # "lightrag" | "pageindex"
    label_vi: str     # short human label (Vietnamese) for UI / docs
    description: str  # one-liner used by the classifier prompt


# Order here is the canonical order used everywhere (prompt, ALL_DOMAINS, docs).
DOMAINS: tuple[DomainInfo, ...] = (
    DomainInfo(
        "HR_POLICY", "hr_policies", "lightrag", "Nội quy lao động",
        "Nội quy lao động, hợp đồng, nghỉ phép, giờ làm việc, đánh giá hiệu suất",
    ),
    DomainInfo(
        "BENEFITS", "benefits", "pageindex", "Phúc lợi & đãi ngộ",
        "Lương thưởng, bảo hiểm sức khỏe, hưu trí, phụ cấp, đãi ngộ",
    ),
    DomainInfo(
        "CONDUCT", "conduct", "lightrag", "Quy tắc ứng xử",
        "Quy tắc ứng xử, đạo đức, quy trình kỷ luật, trang phục",
    ),
    DomainInfo(
        "PROCEDURES", "procedures", "lightrag", "Quy trình & thủ tục",
        "Quy trình từng bước, phê duyệt, onboarding, đề xuất",
    ),
    DomainInfo(
        "HANDBOOK", "handbooks", "lightrag", "Sổ tay nhân viên",
        "Tổng quan công ty, văn hóa, sứ mệnh, thông tin chung nhân viên",
    ),
    DomainInfo(
        "MEDICAL", "medical", "lightrag", "Chính sách y tế",
        "Chính sách y tế, bảo hiểm sức khỏe, danh sách bệnh viện, quy trình khám chữa bệnh",
    ),
    DomainInfo(
        "IT_SECURITY", "it_security", "lightrag", "CNTT & Bảo mật",
        "Chính sách CNTT, bảo mật thông tin, sử dụng thiết bị, mật khẩu, quyền truy cập",
    ),
    DomainInfo(
        "COMPLIANCE", "compliance", "lightrag", "Tuân thủ & Pháp lý",
        "Tuân thủ pháp luật, quy định lao động, bảo vệ dữ liệu, phòng chống tham nhũng",
    ),
    DomainInfo(
        "FINANCE", "finance", "lightrag", "Chính sách tài chính",
        "Chính sách tài chính, hạn mức chi phí, hoàn ứng, phê duyệt ngân sách",
    ),
    DomainInfo(
        "TRAINING", "training", "lightrag", "Đào tạo & Phát triển",
        "Đào tạo, phát triển nhân sự, lộ trình sự nghiệp, học bổng, chứng chỉ",
    ),
)

# --- Derived lookups (build once at import) ---------------------------------

ALL_DOMAINS: list[str] = [d.key for d in DOMAINS]
DOMAIN_BY_KEY: dict[str, DomainInfo] = {d.key: d for d in DOMAINS}
DOC_TYPE_TO_DOMAIN: dict[str, str] = {d.doc_type: d.key for d in DOMAINS}
VALID_DOC_TYPES: set[str] = set(DOC_TYPE_TO_DOMAIN)


def is_valid_domain(key: str) -> bool:
    return key in DOMAIN_BY_KEY


def domain_lines() -> str:
    """Render the domain catalogue as aligned ``KEY — description`` lines.

    Used by the classifier prompt so the prompt and the real domain set can never
    drift apart.
    """
    width = max(len(d.key) for d in DOMAINS)
    return "\n".join(f"  {d.key.ljust(width)} — {d.description}" for d in DOMAINS)


def _assert_schema_in_sync() -> None:
    """Fail fast at import if schemas.DomainKey drifts from this registry.

    Imported lazily to avoid a circular import at module load.
    """
    from app.schemas import DomainKey  # noqa: PLC0415

    literal_keys = set(get_args(DomainKey))
    if literal_keys != set(ALL_DOMAINS):
        missing = set(ALL_DOMAINS) - literal_keys
        extra = literal_keys - set(ALL_DOMAINS)
        raise RuntimeError(
            "schemas.DomainKey is out of sync with domains.DOMAINS — "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
