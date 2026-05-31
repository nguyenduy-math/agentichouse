from __future__ import annotations

import logging

from app.claim_schema import FIELD_META, compute_progress, get_missing_fields
from app.llm import get_provider
from app.prompts import (
    build_confirmation_prompt,
    build_document_continue_prompt,
    build_guide_prompt,
    build_proposal_prompt,
    get_extraction_system,
    get_guide_system,
    get_proposal_system,
)
from app.schemas import (
    ClaimData,
    ClaimDataExtraction,
    ClaimType,
    SessionPhase,
    SessionState,
)

logger = logging.getLogger(__name__)

_OPTIONS_CLAIM_TYPE = ["BHYT ngoại trú", "BHYT nội trú", "Bảo hiểm thương mại"]
_OPTIONS_CONFIRM    = ["Xác nhận, tạo hồ sơ", "Tôi muốn sửa thông tin", "Bắt đầu lại từ đầu"]
_OPTIONS_CORRECTION = ["Vâng, tiếp tục", "Tôi cần sửa thêm"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge(base: ClaimData, patch: ClaimDataExtraction) -> ClaimData:
    base_dict = base.model_dump()
    for field, value in patch.model_dump().items():
        if value is not None:
            base_dict[field] = value
    return ClaimData(**base_dict)


def _is_correction(before: ClaimData, after: ClaimData) -> str | None:
    """Return the first field name that changed from a non-null value, else None."""
    b = before.model_dump()
    a = after.model_dump()
    for field, new_val in a.items():
        if new_val is not None and b.get(field) is not None and b[field] != new_val:
            return field
    return None


def _user_confirms(message: str) -> bool:
    lower = message.lower().strip()
    return any(kw in lower for kw in [
        "xác nhận", "đúng", "ok", "correct", "yes", "đồng ý", "tạo hồ sơ", "1",
    ])


def _user_wants_restart(message: str) -> bool:
    lower = message.lower().strip()
    return any(kw in lower for kw in [
        "bắt đầu lại", "restart", "làm lại", "reset", "3",
    ])


def _user_wants_edit(message: str) -> bool:
    lower = message.lower().strip()
    return any(kw in lower for kw in [
        "sửa", "edit", "thay đổi", "chỉnh", "2",
    ])


# ---------------------------------------------------------------------------
# Gemini calls
# ---------------------------------------------------------------------------

async def _extract(user_message: str, history: list[dict]) -> ClaimDataExtraction:
    context_turns = history[-4:] if len(history) > 4 else history
    messages = [{"role": t["role"], "content": t["content"]} for t in context_turns]
    messages.append({"role": "user", "content": user_message})

    try:
        data = await get_provider().generate_structured(
            messages=messages,
            system=get_extraction_system(),
            temperature=0.0,
            schema=ClaimDataExtraction,
        )
        return ClaimDataExtraction(**data)
    except Exception:
        logger.exception("Extraction call failed; returning empty patch")
        return ClaimDataExtraction()


async def _guide(
    collected: ClaimData,
    missing_fields: list[str],
    history: list[dict],
    correction_field: str | None = None,
    pdf_context: str = "",
) -> str:
    guide_prompt = build_guide_prompt(collected, missing_fields, correction_field)
    context_turns = history[-6:] if len(history) > 6 else history
    messages = [{"role": t["role"], "content": t["content"]} for t in context_turns]
    messages.append({"role": "user", "content": guide_prompt})

    system = get_guide_system()
    if pdf_context:
        system = f"{system}\n\nNGỮ CẢNH TỪ FILE PDF:\n{pdf_context[:3000]}"

    return await get_provider().generate_text(
        messages=messages,
        system=system,
        temperature=0.3,
    )


async def _generate_summary(collected: ClaimData) -> str:
    return await get_provider().generate_text(
        messages=[{"role": "user", "content": build_proposal_prompt(collected)}],
        system=get_proposal_system(),
        temperature=0.2,
    )


def _build_proposal(collected: ClaimData) -> dict:
    claim_type = collected.claim_type or ClaimType.unknown
    type_specific = {
        ClaimType.outpatient: ["insurance_id", "visit_date"],
        ClaimType.inpatient:  ["insurance_id", "admission_date", "discharge_date", "patient_paid"],
        ClaimType.private:    ["policy_number", "event_date", "bank_account"],
        ClaimType.unknown:    [],
    }.get(claim_type, [])

    required = list(set(
        ["claim_type", "name", "dob", "hospital", "diagnosis", "total_cost"] + type_specific
    ))
    collected_dict = collected.model_dump()
    result: dict = {}
    for field in required:
        meta = FIELD_META.get(field)
        label = meta.label_vi if meta else field
        result[label] = collected_dict.get(field)
    result["_raw"] = collected_dict
    return result


async def apply_extracted_fields(
    session: SessionState, fields: ClaimData
) -> tuple[str, ClaimData, dict | None, bool, SessionPhase, list[str] | None]:
    """Merge document-extracted fields into the session, then produce the next
    assistant turn: confirm what was read and ask only for what is still missing.

    Returns the same tuple shape as process_turn.
    """
    merged = _merge(session.collected, ClaimDataExtraction(**fields.model_dump()))
    session.collected = merged

    pdf_ctx = getattr(session, "pdf_context", "")
    claim_type = merged.claim_type or ClaimType.unknown

    # Claim type still unknown — must resolve it before collecting other fields
    if claim_type == ClaimType.unknown:
        reply = await _guide(merged, [], session.history, pdf_context=pdf_ctx)
        return reply, merged, None, False, SessionPhase.identifying, _OPTIONS_CLAIM_TYPE

    missing = get_missing_fields(merged.model_dump(), claim_type)

    # Everything required is present — go straight to confirmation
    if not missing:
        confirmation_text = build_confirmation_prompt(merged)
        return confirmation_text, merged, None, False, SessionPhase.confirming, _OPTIONS_CONFIRM

    # Acknowledge document fields for verification, then ask the next missing one
    guide_prompt = build_document_continue_prompt(merged, missing)
    context_turns = session.history[-6:] if len(session.history) > 6 else session.history
    messages = [{"role": t["role"], "content": t["content"]} for t in context_turns]
    messages.append({"role": "user", "content": guide_prompt})

    system = get_guide_system()
    if pdf_ctx:
        system = f"{system}\n\nNGỮ CẢNH TỪ FILE PDF:\n{pdf_ctx[:3000]}"

    reply = await get_provider().generate_text(messages=messages, system=system, temperature=0.3)
    return reply, merged, None, False, SessionPhase.collecting, None


# ---------------------------------------------------------------------------
# Phase dispatcher
# ---------------------------------------------------------------------------

async def process_turn(
    session: SessionState, user_message: str
) -> tuple[str, ClaimData, dict | None, bool, SessionPhase, list[str] | None]:
    """
    Returns: (reply, updated_collected, proposal, is_complete, new_phase, options)
    """
    phase = session.phase

    # Guard: session already complete — return cached state
    if phase == SessionPhase.complete and session.cached_proposal:
        return (
            "Hồ sơ của bạn đã được tạo. Bạn có thể tải xuống ở thẻ bên dưới.",
            session.collected,
            session.cached_proposal,
            True,
            SessionPhase.complete,
            None,
        )

    pdf_ctx = getattr(session, "pdf_context", "")

    # -----------------------------------------------------------------------
    # Phase: identifying — determine claim type
    # -----------------------------------------------------------------------
    if phase == SessionPhase.identifying:
        extraction = await _extract(user_message, session.history)
        merged = _merge(session.collected, extraction)

        if merged.claim_type and merged.claim_type != ClaimType.unknown:
            # Advance to collecting; ask first real question
            missing = get_missing_fields(merged.model_dump(), merged.claim_type)
            reply = await _guide(merged, missing, session.history, pdf_context=pdf_ctx)
            return reply, merged, None, False, SessionPhase.collecting, None

        # Still unknown — prompt with explicit options
        reply = await _guide(merged, [], session.history, pdf_context=pdf_ctx)
        return reply, merged, None, False, SessionPhase.identifying, _OPTIONS_CLAIM_TYPE

    # -----------------------------------------------------------------------
    # Phase: collecting — gather required fields
    # -----------------------------------------------------------------------
    if phase == SessionPhase.collecting:
        extraction = await _extract(user_message, session.history)
        correction_field = _is_correction(session.collected, _merge(session.collected, extraction))
        merged = _merge(session.collected, extraction)

        claim_type = merged.claim_type or ClaimType.unknown
        missing = get_missing_fields(merged.model_dump(), claim_type)

        if claim_type != ClaimType.unknown and not missing:
            # All fields present → advance to confirming
            confirmation_text = build_confirmation_prompt(merged)
            return (
                confirmation_text,
                merged,
                None,
                False,
                SessionPhase.confirming,
                _OPTIONS_CONFIRM,
            )

        # Still collecting — ask next question (acknowledging correction if any)
        reply = await _guide(merged, missing, session.history, correction_field, pdf_context=pdf_ctx)
        options = _OPTIONS_CORRECTION if correction_field else None
        return reply, merged, None, False, SessionPhase.collecting, options

    # -----------------------------------------------------------------------
    # Phase: confirming — user reviews summary, chooses next action
    # -----------------------------------------------------------------------
    if phase == SessionPhase.confirming:
        if _user_wants_restart(user_message):
            reply = "Đã đặt lại. Bạn muốn khai thác loại hình bảo hiểm nào?"
            return (
                reply,
                ClaimData(),
                None,
                False,
                SessionPhase.identifying,
                _OPTIONS_CLAIM_TYPE,
            )

        if _user_confirms(user_message):
            proposal = _build_proposal(session.collected)
            reply = await _generate_summary(session.collected)
            return reply, session.collected, proposal, True, SessionPhase.complete, None

        # User wants to edit — treat the message as a correction, revert to collecting
        extraction = await _extract(user_message, session.history)
        correction_field = _is_correction(session.collected, _merge(session.collected, extraction))
        merged = _merge(session.collected, extraction)
        claim_type = merged.claim_type or ClaimType.unknown
        missing = get_missing_fields(merged.model_dump(), claim_type)
        reply = await _guide(merged, missing, session.history, correction_field, pdf_context=pdf_ctx)
        return reply, merged, None, False, SessionPhase.collecting, None

    # Should never reach here
    return "Đã xảy ra lỗi. Vui lòng bắt đầu lại.", session.collected, None, False, phase, None
