from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.catalog import filter_by_profile, format_for_prompt, load_catalog
from app.config import settings
from app.health_profile_schema import (
    PROFILE_FIELD_META,
    compute_profile_progress,
    get_field_chips,
    get_missing_profile_fields,
)
from app.prompts import (
    build_profile_confirmation_prompt,
    build_profile_guide_prompt,
    build_recommendation_prompt,
    get_advisor_guide_system,
    get_health_extraction_system,
    get_recommendation_system,
)
from app.schemas import HealthProfile, HealthProfileExtraction, SessionPhase, SessionState

logger = logging.getLogger(__name__)

_OPTIONS_CONFIRM = ["Xác nhận, đề xuất gói bảo hiểm", "Tôi muốn sửa thông tin", "Bắt đầu lại từ đầu"]
_OPTIONS_CORRECTION = ["Vâng, tiếp tục", "Tôi cần sửa thêm"]

_client: genai.Client | None = None


# ---------------------------------------------------------------------------
# Gemini response schema for recommendation output
# ---------------------------------------------------------------------------

class PackageRecommendation(BaseModel):
    rank: int
    package_type: str
    insurer_examples: list[str]
    estimated_premium_range: str
    coverage_highlights: list[str]
    why_suitable: str
    key_considerations: list[str]


class RecommendationOutput(BaseModel):
    recommendations: list[PackageRecommendation]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _merge_profile(base: HealthProfile, patch: HealthProfileExtraction) -> HealthProfile:
    base_dict = base.model_dump()
    for field, value in patch.model_dump().items():
        if value is not None:
            base_dict[field] = value
    return HealthProfile(**base_dict)


def _is_correction(before: HealthProfile, after: HealthProfile) -> str | None:
    b = before.model_dump()
    a = after.model_dump()
    for field, new_val in a.items():
        if new_val is not None and b.get(field) is not None and b[field] != new_val:
            return field
    return None


def _user_confirms(message: str) -> bool:
    lower = message.lower().strip()
    return any(kw in lower for kw in [
        "xác nhận", "đúng", "ok", "correct", "yes", "đồng ý", "đề xuất", "1",
    ])


def _user_wants_restart(message: str) -> bool:
    lower = message.lower().strip()
    return any(kw in lower for kw in ["bắt đầu lại", "restart", "làm lại", "reset", "3"])


# ---------------------------------------------------------------------------
# Gemini calls
# ---------------------------------------------------------------------------

async def _extract(user_message: str, history: list[dict]) -> HealthProfileExtraction:
    context_turns = history[-4:] if len(history) > 4 else history
    contents = [
        types.Content(role=t["role"], parts=[types.Part(text=t["content"])])
        for t in context_turns
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

    try:
        response = await get_client().aio.models.generate_content(
            model=settings.gemini_llm_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=get_health_extraction_system(),
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=HealthProfileExtraction,
            ),
        )
        return HealthProfileExtraction(**json.loads(response.text))
    except Exception:
        logger.exception("Health profile extraction failed; returning empty patch")
        return HealthProfileExtraction()


async def _guide(
    profile: HealthProfile,
    missing_fields: list[str],
    history: list[dict],
    correction_field: str | None = None,
) -> str:
    guide_prompt = build_profile_guide_prompt(profile, missing_fields, correction_field)
    context_turns = history[-6:] if len(history) > 6 else history
    contents = [
        types.Content(role=t["role"], parts=[types.Part(text=t["content"])])
        for t in context_turns
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=guide_prompt)]))

    response = await get_client().aio.models.generate_content(
        model=settings.gemini_llm_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=get_advisor_guide_system(),
            temperature=0.3,
        ),
    )
    return response.text.strip()


async def _generate_recommendation(profile: HealthProfile) -> dict[str, Any]:
    catalog = load_catalog()
    shortlist = filter_by_profile(catalog, profile)
    catalog_text = format_for_prompt(shortlist, profile.monthly_budget_vnd)

    if not shortlist:
        logger.warning("No eligible packages found for profile; using full catalog")
        catalog_text = format_for_prompt(catalog[:6], profile.monthly_budget_vnd)

    response = await get_client().aio.models.generate_content(
        model=settings.gemini_llm_model,
        contents=build_recommendation_prompt(profile, catalog_text),
        config=types.GenerateContentConfig(
            system_instruction=get_recommendation_system(),
            temperature=0.2,
            response_mime_type="application/json",
            response_schema=RecommendationOutput,
        ),
    )
    return json.loads(response.text)


async def _generate_recommendation_intro(recommendation: dict) -> str:
    """Generate a short Vietnamese intro message to accompany the recommendation card."""
    n = len(recommendation.get("recommendations", []))
    response = await get_client().aio.models.generate_content(
        model=settings.gemini_llm_model,
        contents=(
            f"Dựa trên hồ sơ của khách hàng, tôi đã đề xuất {n} loại gói bảo hiểm phù hợp. "
            "Viết 2-3 câu giới thiệu ngắn gọn, thân thiện bằng tiếng Việt, "
            "mời khách hàng xem chi tiết các gói đề xuất bên dưới."
        ),
        config=types.GenerateContentConfig(
            system_instruction=get_advisor_guide_system(),
            temperature=0.3,
        ),
    )
    return response.text.strip()


# ---------------------------------------------------------------------------
# Phase dispatcher
# ---------------------------------------------------------------------------

async def process_turn(
    session: SessionState, user_message: str
) -> tuple[str, HealthProfile, dict | None, bool, SessionPhase, list[str] | None]:
    """
    Returns: (reply, updated_profile, recommendation_or_none, is_complete, new_phase, options)
    """
    phase = session.phase

    # Guard: already complete
    if phase == SessionPhase.complete and session.recommendation:
        return (
            "Gói bảo hiểm đã được đề xuất. Bạn có thể xem chi tiết bên dưới.",
            session.health_profile,
            session.recommendation,
            True,
            SessionPhase.complete,
            None,
        )

    # -----------------------------------------------------------------------
    # Phase: collecting
    # -----------------------------------------------------------------------
    if phase in (SessionPhase.collecting, SessionPhase.identifying):
        extraction = await _extract(user_message, session.history)
        correction_field = _is_correction(
            session.health_profile, _merge_profile(session.health_profile, extraction)
        )
        merged = _merge_profile(session.health_profile, extraction)
        missing = get_missing_profile_fields(merged)

        if not missing:
            # Advance to confirming
            confirmation_text = build_profile_confirmation_prompt(merged)
            return (
                confirmation_text,
                merged,
                None,
                False,
                SessionPhase.confirming,
                _OPTIONS_CONFIRM,
            )

        reply = await _guide(merged, missing, session.history, correction_field)

        # Offer chips for the next field to be filled
        next_field = missing[0]
        chips = get_field_chips(next_field)
        options = _OPTIONS_CORRECTION if correction_field else chips
        return reply, merged, None, False, SessionPhase.collecting, options

    # -----------------------------------------------------------------------
    # Phase: confirming
    # -----------------------------------------------------------------------
    if phase == SessionPhase.confirming:
        if _user_wants_restart(user_message):
            reply = "Đã đặt lại. Hãy cho tôi biết tuổi của bạn để bắt đầu."
            return (
                reply,
                HealthProfile(),
                None,
                False,
                SessionPhase.collecting,
                None,
            )

        if _user_confirms(user_message):
            recommendation = await _generate_recommendation(session.health_profile)
            intro = await _generate_recommendation_intro(recommendation)
            return intro, session.health_profile, recommendation, True, SessionPhase.complete, None

        # User wants to edit — treat as correction
        extraction = await _extract(user_message, session.history)
        correction_field = _is_correction(
            session.health_profile, _merge_profile(session.health_profile, extraction)
        )
        merged = _merge_profile(session.health_profile, extraction)
        missing = get_missing_profile_fields(merged)
        reply = await _guide(merged, missing, session.history, correction_field)
        next_field = missing[0] if missing else None
        chips = get_field_chips(next_field) if next_field else None
        return reply, merged, None, False, SessionPhase.collecting, chips

    return (
        "Đã xảy ra lỗi. Vui lòng bắt đầu lại.",
        session.health_profile,
        None,
        False,
        phase,
        None,
    )


def get_profile_progress(profile: HealthProfile) -> int:
    return compute_profile_progress(profile)
