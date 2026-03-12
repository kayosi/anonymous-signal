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
from app.models.models import Report, ReportAIAnalysis
from app.schemas.schemas import (
    ReportSubmitRequest,
    ReportSubmitResponse,
    ReportDetailResponse,
    ReportListItem,
    PaginatedReports,
    AIAnalysisResponse,
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
    report = Report(
        id=report_id,
        encrypted_content=encrypted_content,
        has_audio=has_audio,
        has_image=has_image,
        audio_ref=audio_ref,
        image_ref=image_ref,
        user_category=request_data.user_category,
        status="pending",
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
        message="Your report has been received anonymously. Thank you for helping keep your community safe.",
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

    import math

    # Step 1: fetch reports (no correlated subquery)
    report_query = (
        select(Report)
        .where(Report.is_archived == False)
        .order_by(desc(Report.submitted_at))
    )
    if status_filter:
        report_query = report_query.where(Report.status == status_filter)

    count_query = select(func.count(Report.id)).where(Report.is_archived == False)
    if status_filter:
        count_query = count_query.where(Report.status == status_filter)
    total = await db.scalar(count_query) or 0

    result = await db.execute(report_query.offset(offset).limit(page_size))
    reports_page = result.scalars().all()

    if not reports_page:
        return PaginatedReports(
            items=[],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(total / page_size)) if total > 0 else 1,
        )

    # Step 2: fetch latest analysis per report using DISTINCT ON
    report_ids = [r.id for r in reports_page]
    from sqlalchemy import text
    analysis_sql = text("""
        SELECT DISTINCT ON (report_id)
            id, report_id, category, urgency_level, severity_score, analyzed_at
        FROM report_ai_analysis
        WHERE report_id = ANY(:ids)
        ORDER BY report_id, analyzed_at DESC
    """)
    analysis_result = await db.execute(analysis_sql, {"ids": report_ids})
    analyses_by_report = {row.report_id: row for row in analysis_result}

    # Step 3: build response
    items = []
    for report in reports_page:
        analysis = analyses_by_report.get(report.id)
        if urgency_filter and (not analysis or analysis.urgency_level != urgency_filter):
            continue
        if category_filter and (not analysis or analysis.category != category_filter):
            continue
        items.append(ReportListItem(
            id=report.id,
            status=report.status,
            user_category=report.user_category,
            submitted_at=report.submitted_at,
            urgency_level=analysis.urgency_level if analysis else None,
            severity_score=analysis.severity_score if analysis else None,
            category=analysis.category if analysis else None,
            has_audio=report.has_audio or False,
            has_image=report.has_image or False,
        ))

    return PaginatedReports(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)) if total > 0 else 1,
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