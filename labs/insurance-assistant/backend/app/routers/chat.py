import sys
import os
import json
import tempfile

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

# Allow direct import of mcp_server tools
_mcp_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "mcp_server"))
if _mcp_root not in sys.path:
    sys.path.insert(0, _mcp_root)

# The vision tools read VISION_PROVIDER and API keys directly from os.environ,
# so load mcp_server/.env here (the backend's pydantic-settings does not populate os.environ).
from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=os.path.join(_mcp_root, ".env"))

from tools.pdf_tool import scan_pdf      # noqa: E402
from tools.image_tool import scan_image  # noqa: E402

from app import advisor_agent, agent as claim_agent
from app.advisor_agent import get_profile_progress
from app.claim_schema import compute_progress
from app.llm import get_provider
from app.prompts import get_extraction_system
from app.schemas import ApplyFieldsRequest, AssistantMode, ChatRequest, ChatResponse, ClaimData, ClaimDataExtraction, ClaimType, HealthProfile, PdfUploadResponse

router = APIRouter(tags=["chat"])

_FIRST_ADVISOR_MSG = (
    "Xin chào! Tôi sẽ giúp bạn tìm gói bảo hiểm phù hợp nhất. "
    "Trước tiên, bạn bao nhiêu tuổi?"
)

# MIME types treated as images
_IMAGE_MIME_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


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


@router.post("/apply-fields", response_model=ChatResponse)
async def apply_fields(body: ApplyFieldsRequest, request: Request) -> ChatResponse:
    """Merge document-extracted fields into the session and let the agent verify
    them and continue asking for any remaining fields."""
    store = request.app.state.session_store
    session = await store.get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    reply, updated_collected, proposal, is_complete, new_phase, options = (
        await claim_agent.apply_extracted_fields(session, body.fields)
    )
    session.collected = updated_collected
    session.history.append({"role": "user", "content": "[Đã tải lên tài liệu và xác nhận thông tin]"})
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


def _is_image_file(filename: str | None, content_type: str | None) -> bool:
    """Determine if uploaded file is an image (vs PDF)."""
    if content_type and content_type.lower() in _IMAGE_MIME_TYPES:
        return True
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        return ext in _IMAGE_EXTENSIONS
    return False


async def _process_upload(
    request: Request,
    session_id: str,
    file: UploadFile,
) -> PdfUploadResponse:
    """Core logic shared by /upload-document and /upload-pdf."""
    store = request.app.state.session_store
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    filename = file.filename or "upload"
    content_type = file.content_type or ""
    is_image = _is_image_file(filename, content_type)

    suffix = os.path.splitext(filename)[1] or (".png" if is_image else ".pdf")

    # Write upload to a temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # ------------------------------------------------------------------
        # Call the appropriate vision tool
        # ------------------------------------------------------------------
        if is_image:
            raw_result = scan_image(file_path=tmp_path)
        else:
            raw_result = scan_pdf(file_path=tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # Parse vision tool result
    # ------------------------------------------------------------------
    try:
        result = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=422, detail="Vision tool returned unexpected output.")

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    extracted_fields: dict = result.get("extracted_fields", {})
    summary_text: str = result.get("summary_text", "")

    # Store document context in session (as JSON text, additive)
    session.pdf_context = json.dumps(extracted_fields, ensure_ascii=False)
    await store.save(session)

    # ------------------------------------------------------------------
    # Build ClaimData from vision-extracted fields
    # ------------------------------------------------------------------
    # The vision provider already returns the backend ClaimType enum values
    # (outpatient/inpatient/private/unknown). Pydantic will coerce them.
    try:
        extracted = ClaimDataExtraction(**{
            k: v for k, v in extracted_fields.items()
            if not k.startswith("_")  # skip internal error keys
        })
    except Exception:
        extracted = ClaimDataExtraction()

    # If vision extraction produced nothing meaningful, fall back to backend LLM
    if not any(getattr(extracted, f, None) for f in extracted.model_fields):
        try:
            data = await get_provider().generate_structured(
                messages=[{"role": "user", "content": f"Trích xuất thông tin từ tài liệu sau:\n\n{raw_result}"}],
                system=get_extraction_system(),
                temperature=0.0,
                schema=ClaimDataExtraction,
            )
            extracted = ClaimDataExtraction(**data)
        except Exception:
            extracted = ClaimDataExtraction()

    return PdfUploadResponse(
        extracted_fields=ClaimData(**extracted.model_dump()),
        summary_text=summary_text,
    )


@router.post("/upload-document", response_model=PdfUploadResponse)
async def upload_document(
    request: Request,
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> PdfUploadResponse:
    """Upload a PDF or image (JPG/PNG) to extract insurance claim fields via vision LLM."""
    return await _process_upload(request, session_id, file)


@router.post("/upload-pdf", response_model=PdfUploadResponse)
async def upload_pdf(
    request: Request,
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> PdfUploadResponse:
    """Backward-compatible alias for /upload-document. Accepts PDF and images."""
    return await _process_upload(request, session_id, file)
