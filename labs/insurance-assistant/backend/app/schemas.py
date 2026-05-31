from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ClaimType(str, Enum):
    outpatient = "outpatient"
    inpatient = "inpatient"
    private = "private"
    unknown = "unknown"


class SessionPhase(str, Enum):
    identifying = "identifying"   # claim_type not yet known (claim flow only)
    collecting  = "collecting"    # gathering required fields
    confirming  = "confirming"    # all fields present, awaiting user confirmation
    complete    = "complete"      # result generated


class AssistantMode(str, Enum):
    claim_filing   = "claim_filing"
    recommendation = "recommendation"


# ---------------------------------------------------------------------------
# Claim-filing data models
# ---------------------------------------------------------------------------

class ClaimData(BaseModel):
    claim_type: ClaimType | None = None
    name: str | None = None
    dob: str | None = None
    insurance_id: str | None = None      # mã BHXH (10 digits)
    policy_number: str | None = None     # private insurance policy number
    hospital: str | None = None
    visit_date: str | None = None        # outpatient: single visit date
    admission_date: str | None = None    # inpatient: check-in date
    discharge_date: str | None = None    # inpatient: check-out date
    event_date: str | None = None        # private: date of insured event
    diagnosis: str | None = None
    diagnosis_code: str | None = None    # ICD-10 if available
    total_cost: float | None = None
    patient_paid: float | None = None    # out-of-pocket after BHYT coverage
    bank_account: str | None = None      # for private reimbursement
    notes: str | None = None


class ClaimDataExtraction(ClaimData):
    """Identical to ClaimData; used as Gemini response_schema so the model
    returns only fields explicitly mentioned in the user message (all others null)."""
    pass


# ---------------------------------------------------------------------------
# Insurance recommendation data models
# ---------------------------------------------------------------------------

class HealthProfile(BaseModel):
    age: int | None = None
    gender: str | None = None               # "nam" / "nữ"
    occupation_type: str | None = None      # "văn phòng" / "ngoài trời" / "lao động nặng"
    pre_existing_conditions: str | None = None  # free text or "không"
    smoker: bool | None = None
    monthly_budget_vnd: float | None = None
    num_insured: int | None = None
    coverage_priority: str | None = None    # comma-separated priorities


class HealthProfileExtraction(HealthProfile):
    """Used as Gemini response_schema for profile extraction."""
    pass


# ---------------------------------------------------------------------------
# Session and API models
# ---------------------------------------------------------------------------

class SessionState(BaseModel):
    session_id: str
    mode: AssistantMode | None = None
    # claim-filing state
    history: list[dict] = []
    collected: ClaimData = ClaimData()
    turn_count: int = 0
    is_complete: bool = False
    phase: SessionPhase = SessionPhase.identifying
    cached_proposal: dict | None = None
    pdf_context: str = ""
    # recommendation state
    health_profile: HealthProfile = HealthProfile()
    recommendation: dict | None = None


class NewSessionRequest(BaseModel):
    mode: AssistantMode


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    collected: ClaimData
    health_profile: HealthProfile = HealthProfile()
    proposal: dict | None = None
    recommendation: dict | None = None
    is_complete: bool
    progress_pct: int
    session_phase: SessionPhase
    options: list[str] | None = None


class NewSessionResponse(BaseModel):
    session_id: str


class HealthResponse(BaseModel):
    status: str


class PdfUploadResponse(BaseModel):
    extracted_fields: ClaimData
    summary_text: str
