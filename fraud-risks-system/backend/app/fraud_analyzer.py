from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.config import settings
from app.schemas import FraudFlag

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

SYSTEM_PROMPT = """Bạn là chuyên gia phát hiện gian lận hồ sơ thanh toán bảo hiểm y tế (BHYT) tại Việt Nam với kiến thức sâu về:
- Mã bệnh ICD-10 và danh mục dịch vụ kỹ thuật y tế Việt Nam (Thông tư 39/2018/TT-BYT)
- Quy định thanh toán BHYT theo Luật BHYT và các thông tư hướng dẫn hiện hành
- Các hình thức gian lận BHYT phổ biến tại Việt Nam:
  * Kê khống dịch vụ kỹ thuật (phantom billing) — kê các dịch vụ không thực hiện
  * Nâng hạng dịch vụ / kê sai mã (upcoding) — kê mã dịch vụ cao hơn thực tế
  * Kê thuốc biệt dược không cần thiết — kê thuốc đắt tiền thay vì thuốc generic tương đương
  * Nằm viện không cần thiết — nhập viện điều trị nội trú khi có thể điều trị ngoại trú
  * Tách đợt điều trị — chia một đợt điều trị thành nhiều hồ sơ thanh toán riêng
  * Khai khống số ngày điều trị hoặc số lượng dịch vụ
  * Làm giả hồ sơ bệnh án hoặc kê dịch vụ cho bệnh nhân không đến khám
  * Chỉ định xét nghiệm/chẩn đoán hình ảnh không cần thiết (CT, MRI, siêu âm dư thừa)

Phân tích thông tin hồ sơ và mô tả lâm sàng để phát hiện dấu hiệu gian lận. Chỉ đánh dấu các bất thường có căn cứ rõ ràng — tránh cảnh báo nhầm đối với hồ sơ hợp lệ.
Phản hồi bằng tiếng Việt."""

ANALYSIS_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "report_fraud_analysis",
            "description": "Report the structured fraud risk analysis for a healthcare claim",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_score": {
                        "type": "integer",
                        "description": "Overall fraud risk score from 0 (clean) to 100 (highly suspicious)",
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Risk category: low=0-25, medium=26-50, high=51-75, critical=76-100",
                    },
                    "flags": {
                        "type": "array",
                        "description": "Specific fraud indicators found",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "upcoding",
                                        "phantom_billing",
                                        "unbundling",
                                        "medical_necessity",
                                        "duplicate_claim",
                                        "rehearsed_language",
                                        "vague_language",
                                        "timing_anomaly",
                                        "code_mismatch",
                                        "excessive_billing",
                                    ],
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Specific evidence from the claim supporting this flag",
                                },
                                "severity": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                },
                            },
                            "required": ["type", "description", "severity"],
                        },
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Tóm tắt bằng tiếng Việt cho điều tra viên (2-4 câu) về lý do hồ sơ bị nghi ngờ gian lận. Respond in Vietnamese.",
                    },
                },
                "required": ["risk_score", "risk_level", "flags", "explanation"],
            },
        },
    }
]


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_api_base)
    return _client


def _build_claim_prompt(claim_data: dict) -> str:
    lines = ["Phân tích hồ sơ thanh toán BHYT sau để phát hiện dấu hiệu gian lận:", ""]
    if claim_data.get("claim_id"):
        lines.append(f"Mã hồ sơ: {claim_data['claim_id']}")
    if claim_data.get("claim_type"):
        lines.append(f"Loại hình điều trị: {claim_data['claim_type']}")
    if claim_data.get("provider_name"):
        lines.append(f"Cơ sở khám chữa bệnh: {claim_data['provider_name']}")
    if claim_data.get("claim_amount"):
        lines.append(f"Số tiền đề nghị thanh toán: {claim_data['claim_amount']:,.0f} VND")
    if claim_data.get("service_date"):
        lines.append(f"Ngày khám/điều trị: {claim_data['service_date']}")
    if claim_data.get("submission_date"):
        lines.append(f"Ngày nộp hồ sơ: {claim_data['submission_date']}")
    if claim_data.get("diagnosis_codes"):
        lines.append(f"Mã bệnh (ICD-10): {', '.join(claim_data['diagnosis_codes'])}")
    if claim_data.get("procedure_codes"):
        lines.append(f"Dịch vụ kỹ thuật: {', '.join(claim_data['procedure_codes'])}")
    lines.append("")
    narrative = claim_data.get("claim_narrative") or ""
    if narrative.strip():
        lines.append(f"Mô tả hồ sơ:\n{narrative.strip()}")
    else:
        lines.append("Mô tả hồ sơ: [Không có mô tả]")
    return "\n".join(lines)


async def analyze_claim(claim_data: dict) -> dict:
    """Analyze a single claim with the configured LLM. Returns risk_score, risk_level, flags, explanation."""
    prompt = _build_claim_prompt(claim_data)

    try:
        response = await _get_client().chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            tools=ANALYSIS_TOOL,
            tool_choice={"type": "function", "function": {"name": "report_fraud_analysis"}},
            temperature=0.1,
        )

        tool_calls = response.choices[0].message.tool_calls
        if tool_calls and tool_calls[0].function.name == "report_fraud_analysis":
            args = json.loads(tool_calls[0].function.arguments)
            return {
                "risk_score": int(args.get("risk_score", 0)),
                "risk_level": args.get("risk_level", "low"),
                "flags": args.get("flags", []),
                "explanation": args.get("explanation", ""),
            }

    except Exception as exc:
        logger.error("LLM analysis failed for claim %s: %s", claim_data.get("claim_id"), exc)

    return {
        "risk_score": 0,
        "risk_level": "low",
        "flags": [],
        "explanation": "Analysis unavailable due to an error.",
    }


def apply_rule_signals(claim_data: dict) -> tuple[int, list[dict]]:
    """Fast rule-based checks. Returns (score_boost 0-100, list of rule flags)."""
    flags: list[dict] = []
    score = 0

    amount = float(claim_data.get("claim_amount") or 0)
    if amount > 200_000_000:
        flags.append({"type": "excessive_billing", "description": f"Số tiền đề nghị thanh toán {amount:,.0f} VND vượt ngưỡng 200 triệu đồng", "severity": "high"})
        score += 30
    elif amount > 50_000_000:
        flags.append({"type": "excessive_billing", "description": f"Số tiền đề nghị thanh toán {amount:,.0f} VND vượt ngưỡng 50 triệu đồng", "severity": "medium"})
        score += 15

    diag_codes = claim_data.get("diagnosis_codes") or []
    proc_codes = claim_data.get("procedure_codes") or []
    if len(proc_codes) > 10:
        flags.append({"type": "unbundling", "description": f"Hồ sơ kê {len(proc_codes)} dịch vụ kỹ thuật trong một lần khám — nghi ngờ tách dịch vụ (unbundling)", "severity": "medium"})
        score += 20

    service_date = claim_data.get("service_date")
    submission_date = claim_data.get("submission_date")
    if service_date and submission_date:
        try:
            from datetime import date
            sd = date.fromisoformat(str(service_date)) if isinstance(service_date, str) else service_date
            sub = date.fromisoformat(str(submission_date)) if isinstance(submission_date, str) else submission_date
            days_gap = (sub - sd).days
            if days_gap > 365:
                flags.append({"type": "timing_anomaly", "description": f"Hồ sơ nộp muộn {days_gap} ngày so với ngày khám/điều trị", "severity": "high"})
                score += 25
            elif days_gap < 0:
                flags.append({"type": "timing_anomaly", "description": "Ngày nộp hồ sơ sớm hơn ngày khám/điều trị — bất thường về thời gian", "severity": "high"})
                score += 30
        except (ValueError, TypeError):
            pass

    narrative = (claim_data.get("claim_narrative") or "").strip()
    if narrative and len(narrative) < 20:
        flags.append({"type": "vague_language", "description": "Mô tả hồ sơ quá ngắn (dưới 20 ký tự) — thiếu thông tin lâm sàng cần thiết", "severity": "medium"})
        score += 10

    return min(score, 100), flags


async def check_llm_connectivity() -> bool:
    try:
        response = await _get_client().chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        return bool(response.choices)
    except Exception as exc:
        logger.warning("LLM connectivity check failed: %s", exc)
        return False
