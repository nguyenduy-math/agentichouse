from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.schemas import HealthProfile

_CATALOG_PATH = Path(__file__).parent.parent / "data" / "packages_catalog.json"
_TOP_N = 6  # max packages passed to Gemini


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def _parse_coverage_priority(priority_str: str | None) -> set[str]:
    if not priority_str:
        return set()
    return {p.strip().lower() for p in priority_str.replace(",", " ").split()}


def _occupation_matches(pkg_occupation: list[str], user_occupation: str | None) -> bool:
    if not user_occupation:
        return True
    user_occ = user_occupation.lower()
    # Map Vietnamese input variations to catalog keys
    if any(k in user_occ for k in ["văn phòng", "office", "desk"]):
        canonical = "văn phòng"
    elif any(k in user_occ for k in ["ngoài trời", "outdoor", "di chuyển"]):
        canonical = "ngoài trời"
    elif any(k in user_occ for k in ["lao động nặng", "heavy", "nặng nhọc", "xây dựng"]):
        canonical = "lao động nặng"
    else:
        canonical = user_occ
    excluded = [e.lower() for e in pkg_occupation]
    return canonical not in excluded


def _score_package(pkg: dict, profile: HealthProfile, user_priorities: set[str]) -> float:
    score = 0.0
    pkg_coverage = {c.lower() for c in pkg.get("coverage_types", [])}
    overlap = len(pkg_coverage & user_priorities)
    score += overlap * 10

    # Prefer packages where a tier fits the budget
    budget = profile.monthly_budget_vnd or 0
    tiers = pkg.get("monthly_premium_tiers", [])
    affordable_tiers = [t for t in tiers if t["budget_max_vnd"] >= budget]
    if affordable_tiers:
        score += 5
    elif tiers:
        cheapest = min(t["budget_max_vnd"] for t in tiers)
        # Slight penalty if cheapest tier is over budget by ≤50%
        if cheapest <= budget * 1.5:
            score += 2

    return score


def filter_by_profile(packages: list[dict], profile: HealthProfile) -> list[dict]:
    """Apply eligibility rules and return top-N scored packages."""
    age = profile.age or 0
    is_smoker = profile.smoker or False
    user_priorities = _parse_coverage_priority(profile.coverage_priority)

    eligible: list[tuple[float, dict]] = []

    for pkg in packages:
        elig = pkg.get("eligibility", {})

        # Hard eligibility filters
        if age and (age < elig.get("min_age", 0) or age > elig.get("max_age", 99)):
            continue
        if is_smoker and elig.get("excludes_smoker", False):
            continue
        excluded_occs = elig.get("excluded_occupations", [])
        if not _occupation_matches(excluded_occs, profile.occupation_type):
            continue

        score = _score_package(pkg, profile, user_priorities)
        eligible.append((score, pkg))

    eligible.sort(key=lambda x: x[0], reverse=True)
    return [pkg for _, pkg in eligible[:_TOP_N]]


def _best_tier(tiers: list[dict], budget: float | None) -> dict | None:
    if not tiers:
        return None
    if budget is None:
        return tiers[0]
    affordable = [t for t in tiers if t["budget_max_vnd"] >= budget]
    if affordable:
        return min(affordable, key=lambda t: t["budget_max_vnd"])
    return min(tiers, key=lambda t: t["budget_max_vnd"])


def format_for_prompt(packages: list[dict], budget: float | None = None) -> str:
    """Format shortlisted packages as structured text for the Gemini prompt."""
    if not packages:
        return "(Không tìm thấy gói nào phù hợp với tiêu chí lọc)"

    lines: list[str] = []
    for i, pkg in enumerate(packages, 1):
        tier = _best_tier(pkg.get("monthly_premium_tiers", []), budget)
        tier_str = (
            f"{tier['plan']} — phí ~{tier['budget_max_vnd']:,.0f} VNĐ/tháng, "
            f"quyền lợi tối đa {tier['sum_insured_vnd']:,.0f} VNĐ/năm"
            if tier else "liên hệ để biết phí"
        )
        benefits = "\n    ".join(f"• {b}" for b in pkg.get("key_benefits_vi", []))
        exclusions = "; ".join(pkg.get("exclusions_vi", []))
        lines.append(
            f"[Gói {i}]\n"
            f"  Công ty: {pkg['insurer']}\n"
            f"  Tên sản phẩm: {pkg['name']}\n"
            f"  Loại: {pkg['product_line']}\n"
            f"  Phạm vi bảo hiểm: {', '.join(pkg.get('coverage_types', []))}\n"
            f"  Gói phù hợp ngân sách: {tier_str}\n"
            f"  Quyền lợi nổi bật:\n    {benefits}\n"
            f"  Điều khoản loại trừ chính: {exclusions}\n"
            f"  Mô tả: {pkg.get('description_vi', '')}"
        )
    return "\n\n".join(lines)
