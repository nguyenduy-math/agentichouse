import sys
import os
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

# Allow direct import of mcp_server tools
_mcp_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp_server"))
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

from tools.pdf_tool import scan_pdf  # noqa: E402

from app import advisor_agent, agent as claim_agent
from app.advisor_agent import get_profile_progress
from app.claim_schema import compute_progress
from app.llm import get_provider
from app.prompts import get_extraction_system
from app.schemas import AssistantMode, ChatRequest, ChatResponse, ClaimData, ClaimDataExtraction, ClaimType, HealthProfile, PdfUploadResponse

router = APIRouter(tags=["chat"])

_FIRST_ADVISOR_MSG = (
    "Xin chào! Tôi sẽ giúp bạn tìm gói bảo hiểm phù hợp nhất. "
    "Trước tiên, bạn bao nhiêu tuổi?"
)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    store = request.app.state.session_store

    if body.session_id:
        session = await store.get(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found or expired")
    else:
        raise HTTPException(status_code=400, detail="session_id is required")

    mode = session.mode

    # -----------------------------------------------------------------------
    # Dispatch to the correct agent
    # -----------------------------------------------------------------------
    if mode == AssistantMode.recommendation:
        reply, updated_profile, recommendation, is_complete, new_phase, options = (
            await advisor_agent.process_turn(session, body.message)
        )
        session.health_profile = updated_profile
        session.history.append({"role": "user", "content": body.message})
        session.history.append({"role": "model", "content": reply})
        session.turn_count += 1
        session.is_complete = is_complete
        session.phase = new_phase
        if recommendation:
            session.recommendation = recommendation
        await store.save(session)

        progress = get_profile_progress(updated_profile)
        return ChatResponse(
            session_id=session.session_id,
            reply=reply,
            collected=session.collected,
            health_profile=updated_profile,
            recommendation=recommendation,
            is_complete=is_complete,
            progress_pct=progress,
            session_phase=new_phase,
            options=options,
        )

    else:  # claim_filing (default)
        reply, updated_collected, proposal, is_complete, new_phase, options = (
            await claim_agent.process_turn(session, body.message)
        )
        session.collected = updated_collected
        session.history.append({"role": "user", "content": body.message})
        session.history.append({"role": "model", "content": reply})
        session.turn_count += 1
        session.is_complete = is_complete
        session.phase = new_phase
        if proposal:
            session.cached_proposal = proposal
        await store.save(session)

        claim_type = updated_collected.claim_type or ClaimType.unknown
        progress = compute_progress(updated_collected.model_dump(), claim_type)
        return ChatResponse(
            session_id=session.session_id,
            reply=reply,
            collected=updated_collected,
            health_profile=HealthProfile(),
            proposal=proposal,
            is_complete=is_complete,
            progress_pct=progress,
            session_phase=new_phase,
            options=options,
        )


@router.post("/upload-pdf", response_model=PdfUploadResponse)
async def upload_pdf(
    request: Request,
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> PdfUploadResponse:
    store = request.app.state.session_store
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    # Save uploaded PDF to a temp file
    suffix = os.path.splitext(file.filename or "upload.pdf")[1] or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        pdf_text = scan_pdf(file_path=tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if pdf_text.startswith("Error"):
        raise HTTPException(status_code=422, detail=pdf_text)

    # Store PDF context in session (additive)
    session.pdf_context = pdf_text
    await store.save(session)

    # Extract claim fields from PDF text via LLM
    try:
        data = await get_provider().generate_structured(
            messages=[{"role": "user", "content": f"Trích xuất thông tin từ tài liệu PDF sau:\n\n{pdf_text}"}],
            system=get_extraction_system(),
            temperature=0.0,
            schema=ClaimDataExtraction,
        )
        extracted = ClaimDataExtraction(**data)
    except Exception:
        extracted = ClaimDataExtraction()

    # Build summary text
    field_labels = {
        "claim_type": "Loại bảo hiểm",
        "name": "Họ tên",
        "dob": "Ngày sinh",
        "insurance_id": "Mã BHXH",
        "policy_number": "Số hợp đồng",
        "hospital": "Bệnh viện",
        "visit_date": "Ngày khám",
        "admission_date": "Ngày nhập viện",
        "discharge_date": "Ngày xuất viện",
        "event_date": "Ngày xảy ra sự kiện",
        "diagnosis": "Chẩn đoán",
        "diagnosis_code": "Mã ICD-10",
        "total_cost": "Tổng chi phí",
        "patient_paid": "Bệnh nhân tự trả",
        "bank_account": "Tài khoản ngân hàng",
        "notes": "Ghi chú",
    }
    found_lines = []
    for field, label in field_labels.items():
        val = getattr(extracted, field, None)
        if val is not None:
            found_lines.append(f"- {label}: {val}")

    if found_lines:
        summary = (
            "Tôi đã đọc file PDF và tìm thấy các thông tin sau:\n"
            + "\n".join(found_lines)
            + "\n\nBạn có muốn điền vào form không?"
        )
    else:
        summary = "Tôi đã đọc file PDF nhưng không tìm thấy thông tin bảo hiểm nào. Bạn có thể nhập thông tin thủ công."

    return PdfUploadResponse(
        extracted_fields=ClaimData(**extracted.model_dump()),
        summary_text=summary,
    )
