"""
Reports API Endpoints
======================
Handles anonymous report submission and retrieval.

PRIVACY RULES for this module:
  1. NEVER log request.client.host
  2. NEVER access request.headers["user-agent"]
  3. All content encrypted before DB write
  4. Submission endpoint has NO auth requirement (anonymous)
  5. Read endpoints require analyst authentication
"""

import json
import uuid
from typing import Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import desc, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.models import Report, ReportAIAnalysis, ReportMessage
from app.schemas.schemas import (
    ReportSubmitRequest,
    ReportDetailResponse,
    ReportListItem,
    PaginatedReports,
    AIAnalysisResponse,
    ReportSubmitResponse,
    ReportTrackResponse,
    ReportMessageOut,
    SendMessageRequest,
    AnalystSendMessageRequest,
)
from app.security.encryption import encryption_service, FileEncryptionService
from app.core.config import settings
from app.api.v1.auth import get_current_analyst

logger = structlog.get_logger(__name__)
router = APIRouter()

# Max file sizes
MAX_AUDIO_BYTES = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024
MAX_IMAGE_BYTES = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024

# Allowed MIME types
ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post(
    "/submit",
    response_model=ReportSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit anonymous report",
    description=(
        "Submit an anonymous report. "
        "No authentication required. "
        "IP and device information is NEVER stored."
    ),
)
async def submit_report(
    # Form fields (supports multipart for file uploads)
    text_content: Optional[str] = Form(None),
    user_category: Optional[str] = Form(None),
    location_hint: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Anonymous report submission endpoint.

    Accepts text, audio, and/or image. All content is:
    1. Metadata stripped (from files)
    2. Encrypted before storage
    3. Queued for AI processing
    """
    # ── Validate at least one content type provided ────────────────────────
    if not text_content and not audio_file and not image_file:
        raise HTTPException(
            status_code=422,
            detail="At least one of text_content, audio_file, or image_file is required"
        )

    # ── Validate category ─────────────────────────────────────────────────
    request_data = ReportSubmitRequest(
        text_content=text_content,
        user_category=user_category,
        location_hint=location_hint,
    )

    file_svc = FileEncryptionService(
        upload_dir=settings.UPLOAD_DIR,
        encryption=encryption_service,
    )

    report_id = uuid.uuid4()
    audio_ref = None
    image_ref = None
    has_audio = False
    has_image = False

    # ── Process Audio File ─────────────────────────────────────────────────
    if audio_file:
        # Validate file type
        content_type = audio_file.content_type or ""
        if content_type not in ALLOWED_AUDIO_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported audio format. Allowed: {ALLOWED_AUDIO_TYPES}"
            )

        audio_data = await audio_file.read()

        if len(audio_data) > MAX_AUDIO_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Audio file too large. Max: {settings.MAX_AUDIO_SIZE_MB}MB"
            )

        audio_ref = encryption_service.generate_anonymous_file_ref(
            audio_file.filename or "audio", str(report_id)
        )
        await file_svc.save_encrypted_file(audio_data, audio_ref, content_type)
        has_audio = True
        logger.info("audio_file_processed", report_id=str(report_id)[:8])

    # ── Process Image File ─────────────────────────────────────────────────
    if image_file:
        content_type = image_file.content_type or ""
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported image format. Allowed: {ALLOWED_IMAGE_TYPES}"
            )

        image_data = await image_file.read()

        if len(image_data) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Image too large. Max: {settings.MAX_IMAGE_SIZE_MB}MB"
            )

        image_ref = encryption_service.generate_anonymous_file_ref(
            image_file.filename or "image", str(report_id)
        )
        # Image metadata stripping happens inside save_encrypted_file
        await file_svc.save_encrypted_file(image_data, image_ref, content_type)
        has_image = True
        logger.info("image_file_processed", report_id=str(report_id)[:8])

    # ── Encrypt Report Content ─────────────────────────────────────────────
    content_payload = json.dumps({
        "text": request_data.text_content or "",
        "location_hint": request_data.location_hint or "",
        # PRIVACY: Location hint is general area, NOT GPS coordinates
    })

    encrypted_content = encryption_service.encrypt(content_payload)

    # ── Save to Database ───────────────────────────────────────────────────
    # ── Generate anonymous tracking code ─────────────────────────────────
    import secrets, string
    from passlib.hash import bcrypt as pw_bcrypt
    alphabet = string.ascii_uppercase + string.digits
    part1 = "".join(secrets.choice(alphabet) for _ in range(4))
    part2 = "".join(secrets.choice(alphabet) for _ in range(4))
    tracking_code = f"KE-{part1}-{part2}"
    tracking_code_hash = pw_bcrypt.hash(tracking_code)

    report = Report(
        id=report_id,
        encrypted_content=encrypted_content,
        has_audio=has_audio,
        has_image=has_image,
        audio_ref=audio_ref,
        image_ref=image_ref,
        user_category=request_data.user_category,
        status="pending",
        tracking_code_hash=tracking_code_hash,
    )

    db.add(report)
    await db.commit()
    await db.refresh(report)

    logger.info("report_submitted", report_id=str(report_id)[:8], has_audio=has_audio, has_image=has_image)

    # ── Trigger AI Processing (async, non-blocking) ────────────────────────
    await _trigger_ai_processing(str(report_id))

    return ReportSubmitResponse(
        report_id=report_id,
        status="received",
        message="Your report has been received anonymously. Save your tracking code to check status and receive messages from analysts.",
        tracking_code=tracking_code,
    )


async def _trigger_ai_processing(report_id: str) -> None:
    """
    Send report to AI service for async processing.
    Non-blocking — failure here does not fail the submission.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.AI_SERVICE_URL}/process/{report_id}",
                json={"report_id": report_id},
            )
        logger.info("ai_processing_triggered", report_id=report_id[:8])
    except Exception as e:
        # AI service unavailable — report saved, processing will retry
        logger.warning("ai_trigger_failed", error=str(e), report_id=report_id[:8])


# ─── Analyst Endpoints (Require Auth) ──────────────────────────────────────

@router.get(
    "/",
    response_model=PaginatedReports,
    summary="List reports (analyst only)",
    dependencies=[Depends(get_current_analyst)],
)
async def list_reports(
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    urgency_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List reports with pagination and filtering for analyst dashboard."""
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    # Step 1: get latest analysis id per report using DISTINCT ON (avoids SQLAlchemy auto-correlation bug)
    from sqlalchemy import text
    latest_analysis_ids_result = await db.execute(
        text("""
            SELECT DISTINCT ON (report_id) id, report_id, urgency_level, severity_score, category
            FROM report_ai_analysis
            ORDER BY report_id, analyzed_at DESC
        """)
    )
    latest_by_report = {row.report_id: row for row in latest_analysis_ids_result}

    # Step 2: fetch reports with filters
    base_conditions = [Report.is_archived == False]
    if status_filter:
        base_conditions.append(Report.status == status_filter)
    if category_filter:
        base_conditions.append(Report.user_category == category_filter)

    query = (
        select(Report)
        .where(*base_conditions)
        .order_by(desc(Report.submitted_at))
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(query)
    reports = result.scalars().all()

    # Build rows as (report, analysis_row_or_None)
    rows = [(r, latest_by_report.get(r.id)) for r in reports]

    # Count query
    count_query = select(func.count(Report.id)).where(*base_conditions)
    total = await db.scalar(count_query)

    items = []
    for report, analysis in rows:
        urgency = analysis.urgency_level if analysis else None
        if urgency_filter and urgency != urgency_filter:
            continue
        item = ReportListItem(
            id=report.id,
            status=report.status,
            user_category=report.user_category,
            submitted_at=report.submitted_at,
            urgency_level=urgency,
            severity_score=analysis.severity_score if analysis else None,
            category=analysis.category if analysis else None,
        )
        items.append(item)

    return PaginatedReports(
        items=items,
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{report_id}",
    response_model=ReportDetailResponse,
    summary="Get report detail (analyst only)",
    dependencies=[Depends(get_current_analyst)],
)
async def get_report(
    report_id: uuid.UUID,
    include_content: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Get full report detail including AI analyses."""
    result = await db.execute(
        select(Report)
        .options(selectinload(Report.ai_analyses))
        .where(Report.id == report_id, Report.is_archived == False)
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    decrypted_text = None
    if include_content:
        try:
            content = json.loads(encryption_service.decrypt(report.encrypted_content))
            decrypted_text = content.get("text")
        except Exception:
            decrypted_text = "[Content decryption failed]"

    analyses = [
        AIAnalysisResponse(
            id=a.id,
            report_id=a.report_id,
            category=a.category,
            subcategory=a.subcategory,
            confidence_score=a.confidence_score,
            severity_score=a.severity_score,
            urgency_level=a.urgency_level,
            classification_reasoning=a.classification_reasoning,
            severity_reasoning=a.severity_reasoning,
            transcription=a.transcription,
            transcription_confidence=a.transcription_confidence,
            ai_summary=a.ai_summary,
            cluster_id=a.cluster_id,
            analyzed_at=a.analyzed_at,
            model_version=a.model_version,
        )
        for a in report.ai_analyses
    ]

    return ReportDetailResponse(
        id=report.id,
        status=report.status,
        user_category=report.user_category,
        submitted_at=report.submitted_at,
        processed_at=report.processed_at,
        has_audio=report.has_audio,
        has_image=report.has_image,
        decrypted_text=decrypted_text,
        ai_analyses=analyses,
    )


# ─── Reporter Tracking Endpoints (No Auth — Code Only) ─────────────────────

@router.post(
    "/track",
    response_model=ReportTrackResponse,
    summary="Track report status using anonymous code",
)
async def track_report(
    tracking_code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Reporter uses their one-time code to check report status and read analyst messages.
    No authentication required — the code IS the identity.
    """
    from passlib.hash import bcrypt as pw_bcrypt
    from sqlalchemy import text as sql_text

    # Find report by trying bcrypt verify against all hashed codes
    # For performance we use a partial index — only check non-null codes
    result = await db.execute(
        select(Report)
        .where(Report.tracking_code_hash.isnot(None))
        .where(Report.is_archived == False)
    )
    reports = result.scalars().all()

    matched_report = None
    for r in reports:
        try:
            if pw_bcrypt.verify(tracking_code, r.tracking_code_hash):
                matched_report = r
                break
        except Exception:
            continue

    if not matched_report:
        raise HTTPException(status_code=404, detail="Tracking code not found")

    # Fetch latest AI analysis
    analysis_result = await db.execute(
        select(ReportAIAnalysis)
        .where(ReportAIAnalysis.report_id == matched_report.id)
        .order_by(desc(ReportAIAnalysis.analyzed_at))
        .limit(1)
    )
    analysis = analysis_result.scalar_one_or_none()

    # Fetch messages
    msg_result = await db.execute(
        select(ReportMessage)
        .where(ReportMessage.report_id == matched_report.id)
        .order_by(ReportMessage.created_at)
    )
    messages = msg_result.scalars().all()

    # Mark analyst messages as read by reporter
    unread_count = sum(1 for m in messages if m.sender == "analyst" and not m.read_by_reporter)
    if unread_count > 0:
        from sqlalchemy import update as sql_update
        await db.execute(
            sql_update(ReportMessage)
            .where(ReportMessage.report_id == matched_report.id)
            .where(ReportMessage.sender == "analyst")
            .values(read_by_reporter=True)
        )
        await db.commit()

    return ReportTrackResponse(
        report_id=matched_report.id,
        status=matched_report.status,
        user_category=matched_report.user_category,
        submitted_at=matched_report.submitted_at,
        urgency_level=analysis.urgency_level if analysis else None,
        category=analysis.category if analysis else None,
        messages=[ReportMessageOut(
            id=m.id,
            sender=m.sender,
            message=m.message,
            created_at=m.created_at,
        ) for m in messages],
        unread_from_analyst=unread_count,
    )


@router.post(
    "/track/message",
    summary="Reporter sends message using tracking code",
    status_code=status.HTTP_201_CREATED,
)
async def reporter_send_message(
    tracking_code: str = Form(...),
    message: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Reporter replies to analyst using their tracking code."""
    from passlib.hash import bcrypt as pw_bcrypt

    if not message or len(message.strip()) < 1:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    if len(message) > 2000:
        raise HTTPException(status_code=422, detail="Message too long (max 2000 chars)")

    result = await db.execute(
        select(Report)
        .where(Report.tracking_code_hash.isnot(None))
        .where(Report.is_archived == False)
    )
    reports = result.scalars().all()

    matched_report = None
    for r in reports:
        try:
            if pw_bcrypt.verify(tracking_code, r.tracking_code_hash):
                matched_report = r
                break
        except Exception:
            continue

    if not matched_report:
        raise HTTPException(status_code=404, detail="Tracking code not found")

    msg = ReportMessage(
        report_id=matched_report.id,
        sender="reporter",
        message=message.strip(),
        read_by_analyst=False,
        read_by_reporter=True,
    )
    db.add(msg)
    await db.commit()

    return {"status": "sent", "message": "Your message has been sent to the analyst."}


# ─── Analyst Chat Endpoints (Require Auth) ─────────────────────────────────

@router.get(
    "/{report_id}/messages",
    response_model=list[ReportMessageOut],
    summary="Get messages for a report (analyst only)",
    dependencies=[Depends(get_current_analyst)],
)
async def get_report_messages(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Analyst reads all messages for a report."""
    result = await db.execute(
        select(ReportMessage)
        .where(ReportMessage.report_id == report_id)
        .order_by(ReportMessage.created_at)
    )
    messages = result.scalars().all()

    # Mark reporter messages as read by analyst
    from sqlalchemy import update as sql_update
    await db.execute(
        sql_update(ReportMessage)
        .where(ReportMessage.report_id == report_id)
        .where(ReportMessage.sender == "reporter")
        .values(read_by_analyst=True)
    )
    await db.commit()

    return [ReportMessageOut(
        id=m.id,
        sender=m.sender,
        message=m.message,
        created_at=m.created_at,
    ) for m in messages]


@router.post(
    "/{report_id}/messages",
    response_model=ReportMessageOut,
    summary="Analyst sends message to reporter",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_analyst)],
)
async def analyst_send_message(
    report_id: uuid.UUID,
    body: AnalystSendMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Analyst initiates or replies in the chat for a report."""
    # Verify report exists
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    msg = ReportMessage(
        report_id=report_id,
        sender="analyst",
        message=body.message.strip(),
        read_by_analyst=True,
        read_by_reporter=False,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    logger.info("analyst_message_sent", report_id=str(report_id)[:8])

    return ReportMessageOut(
        id=msg.id,
        sender=msg.sender,
        message=msg.message,
        created_at=msg.created_at,
    )


# ─── Spam Box Endpoints ────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone

@router.get(
    "/spam",
    summary="List spam/flagged reports (analyst only)",
    dependencies=[Depends(get_current_analyst)],
)
async def list_spam_reports(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Return reports flagged as spam/low-credibility, sorted by flagged date."""
    offset = (page - 1) * page_size

    total_result = await db.execute(
        select(func.count(Report.id)).where(
            Report.status == "flagged",
            Report.is_archived == False,
        )
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(Report)
        .where(Report.status == "flagged", Report.is_archived == False)
        .order_by(desc(Report.spam_flagged_at))
        .offset(offset)
        .limit(page_size)
    )
    reports = result.scalars().all()

    import json as _json
    items = []
    for r in reports:
        auto_delete_in_days = None
        if r.spam_deleted_at:
            delta = r.spam_deleted_at - datetime.now(timezone.utc)
            auto_delete_in_days = max(0, delta.days)

        flags = []
        if r.credibility_flags:
            try:
                flags = _json.loads(r.credibility_flags)
            except Exception:
                flags = [r.credibility_flags]

        items.append({
            "id": str(r.id),
            "user_category": r.user_category,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "spam_flagged_at": r.spam_flagged_at.isoformat() if r.spam_flagged_at else None,
            "spam_reason": r.spam_reason or "Flagged by automated credibility check",
            "credibility_score": r.credibility_score,
            "credibility_flags": flags,
            "duplicate_of": r.duplicate_of,
            "auto_delete_in_days": auto_delete_in_days,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post(
    "/spam/{report_id}/restore",
    summary="Restore spam report back to pending (analyst only)",
    dependencies=[Depends(get_current_analyst)],
)
async def restore_spam_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Move a spam-flagged report back to pending for re-analysis."""
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.is_archived == False)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status != "flagged":
        raise HTTPException(status_code=400, detail="Report is not in spam box")

    report.status = "pending"
    report.spam_reason = None
    report.credibility_score = None
    report.credibility_flags = None
    report.duplicate_of = None
    report.spam_flagged_at = None
    report.spam_deleted_at = None
    await db.commit()

    logger.info("spam_report_restored", report_id=str(report_id)[:8])
    return {"status": "restored", "report_id": str(report_id)}


@router.delete(
    "/spam/{report_id}",
    summary="Permanently delete a spam report (analyst only)",
    dependencies=[Depends(get_current_analyst)],
)
async def delete_spam_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Permanently archive/delete a spam report."""
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.is_archived == False)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.is_archived = True
    await db.commit()

    logger.info("spam_report_deleted", report_id=str(report_id)[:8])
    return {"status": "deleted", "report_id": str(report_id)}