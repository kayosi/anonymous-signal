"""
AI Service — Main Inference Orchestrator
==========================================
FastAPI microservice that processes reports through the full AI pipeline:
  1. Decrypt & load report content
  2. Transcribe audio (if present)
  3. Classify text into categories
  4. Score severity & urgency
  5. Generate embedding + assign cluster
  6. Generate AI summary
  7. Write analysis back to database
  8. Trigger alerts if needed

This service runs ONLY on the internal Docker network.
It is NOT exposed to the public internet.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Local imports
from classifier import get_classifier
from clustering import get_clustering_service, get_embedding_service
from scoring import get_scorer
from transcription import get_transcription_service

logger = structlog.get_logger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://anon_user:password@postgres:5432/anon_signal"
)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/encrypted_uploads")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
AI_MODEL_VERSION = "v1.0-bart-whisper-minilm"

# ─── Database ─────────────────────────────────────────────────────────────────
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# ─── Encryption (inline, to avoid importing backend app) ──────────────────────
def get_encryption_service():
    from cryptography.fernet import Fernet
    class SimpleEncryption:
        def __init__(self, key: str):
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key) if key else None

        def decrypt(self, ciphertext: str) -> str:
            if not self.fernet or not ciphertext:
                return ""
            return self.fernet.decrypt(ciphertext.encode()).decode()

        def decrypt_bytes(self, data: bytes) -> bytes:
            if not self.fernet:
                return data
            return self.fernet.decrypt(data)

    return SimpleEncryption(ENCRYPTION_KEY)


# ─── FastAPI App ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Anonymous Signal AI Service",
    description="Internal AI processing microservice",
    docs_url=None,  # Internal only — no docs
    redoc_url=None,
)


class ProcessRequest(BaseModel):
    report_id: str


@app.get("/health")
async def health():
    return {"status": "operational", "service": "ai-processor"}


@app.post("/process/{report_id}")
async def process_report(
    report_id: str,
    background_tasks: BackgroundTasks,
):
    """
    Trigger AI processing for a report.
    Runs asynchronously in background — returns immediately.
    """
    background_tasks.add_task(_run_ai_pipeline, report_id)
    return {"status": "queued", "report_id": report_id}


async def _run_ai_pipeline(report_id: str):
    """
    Full AI processing pipeline for a single report.
    This is the core intelligence engine.
    """
    logger.info("ai_pipeline_starting", report_id=report_id[:8])

    encryption = get_encryption_service()
    classifier = get_classifier()
    scorer = get_scorer()
    transcription_svc = get_transcription_service(WHISPER_MODEL)
    clustering_svc = get_clustering_service()
    embedding_svc = get_embedding_service()

    async with AsyncSessionLocal() as db:
        try:
            # ── 1. Load Report ────────────────────────────────────────────
            from sqlalchemy import text as sql_text
            result = await db.execute(
                sql_text(
                    "SELECT id, encrypted_content, has_audio, audio_ref, "
                    "has_image, image_ref, user_category, status "
                    "FROM reports WHERE id = :id AND is_archived = false"
                ),
                {"id": report_id},
            )
            row = result.fetchone()

            if not row:
                logger.error("report_not_found", report_id=report_id[:8])
                return

            if row.status == "analyzed":
                logger.info("report_already_analyzed", report_id=report_id[:8])
                return

            # Mark as processing
            await db.execute(
                sql_text("UPDATE reports SET status = 'processing' WHERE id = :id"),
                {"id": report_id},
            )
            await db.commit()

            # ── 2. Decrypt Content ────────────────────────────────────────
            try:
                content_json = encryption.decrypt(row.encrypted_content)
                content = json.loads(content_json)
                text_content = content.get("text", "")
            except Exception as e:
                logger.error("decrypt_failed", error=str(e))
                text_content = ""

            # ── 3. Transcribe Audio ───────────────────────────────────────
            transcription = ""
            transcription_confidence = 0.0

            if row.has_audio and row.audio_ref:
                logger.info("transcribing_audio", report_id=report_id[:8])
                transcription, transcription_confidence = (
                    await transcription_svc.transcribe_from_file_ref(
                        file_ref=row.audio_ref,
                        upload_dir=UPLOAD_DIR,
                        encryption_service=encryption,
                    )
                )

            # ── 4. Combine Text Sources ───────────────────────────────────
            # Use transcription if no text, or combine both
            combined_text = ""
            if text_content and transcription:
                combined_text = f"{text_content}\n{transcription}"
            elif text_content:
                combined_text = text_content
            elif transcription:
                combined_text = transcription
            else:
                combined_text = "No content available"

            # ── 5. Classify ───────────────────────────────────────────────
            logger.info("classifying_report", report_id=report_id[:8])
            classification = await classifier.classify(combined_text)

            # Use user category as hint if AI confidence is low
            category = classification["category"]
            if classification["confidence"] < 0.4 and row.user_category:
                category = row.user_category
                classification["reasoning"] += f" (User hint applied: {row.user_category})"

            # ── 6. Score Severity ─────────────────────────────────────────
            severity_result = scorer.score(
                text=combined_text,
                category=category,
                classification_confidence=classification["confidence"],
            )

            # ── 7. Generate Embedding ─────────────────────────────────────
            embedding = embedding_svc.encode(combined_text)

            # ── 8. Cluster Assignment ─────────────────────────────────────
            cluster_id = await clustering_svc.assign_cluster(
                report_id=report_id,
                text=combined_text,
                category=category,
                db=db,
                alert_service=None,
            )

            # ── 9. Generate AI Summary ────────────────────────────────────
            ai_summary = scorer.generate_ai_summary(
                text=combined_text,
                category=category,
                severity=severity_result["severity_score"],
                urgency=severity_result["urgency_level"],
                transcription=transcription if transcription else None,
            )

            # ── 10. Save Analysis ─────────────────────────────────────────
            analysis_id = str(uuid.uuid4())
            await db.execute(
                sql_text("""
                    INSERT INTO report_ai_analysis (
                        id, report_id, category, subcategory, confidence_score,
                        severity_score, urgency_level,
                        classification_reasoning, severity_reasoning,
                        embedding, cluster_id,
                        model_version, analyzed_at,
                        transcription, transcription_confidence, ai_summary
                    ) VALUES (
                        :id, :report_id, :category, :subcategory, :confidence,
                        :severity, :urgency,
                        :class_reason, :sev_reason,
                        :embedding, :cluster_id,
                        :model_version, NOW(),
                        :transcription, :trans_confidence, :summary
                    )
                """),
                {
                    "id": analysis_id,
                    "report_id": report_id,
                    "category": category,
                    "subcategory": classification.get("subcategory"),
                    "confidence": classification["confidence"],
                    "severity": severity_result["severity_score"],
                    "urgency": severity_result["urgency_level"],
                    "class_reason": classification["reasoning"],
                    "sev_reason": severity_result["severity_reasoning"],
                    "embedding": embedding if embedding else None,
                    "cluster_id": cluster_id,
                    "model_version": AI_MODEL_VERSION,
                    "transcription": transcription or None,
                    "trans_confidence": transcription_confidence or None,
                    "summary": ai_summary,
                },
            )

            # ── 11. Update Report Status ──────────────────────────────────
            await db.execute(
                sql_text(
                    "UPDATE reports SET status = 'analyzed', processed_at = NOW() WHERE id = :id"
                ),
                {"id": report_id},
            )

            await db.commit()

            logger.info(
                "ai_pipeline_complete",
                report_id=report_id[:8],
                category=category,
                severity=severity_result["severity_score"],
                urgency=severity_result["urgency_level"],
                cluster_id=cluster_id[:8] if cluster_id else None,
            )

        except Exception as e:
            logger.error("ai_pipeline_failed", report_id=report_id[:8], error=str(e))
            # Mark as failed
            try:
                await db.execute(
                    sql_text("UPDATE reports SET status = 'pending' WHERE id = :id"),
                    {"id": report_id},
                )
                await db.commit()
            except Exception:
                pass


if __name__ == "__main__":
    uvicorn.run(
        "inference:app",
        host="0.0.0.0",
        port=8001,
        access_log=False,  # Internal service — no logging
        log_level="warning",
    )
