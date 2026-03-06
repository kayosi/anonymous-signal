"""
AI Service — Main Inference Orchestrator
==========================================
FastAPI microservice that processes reports through the full AI pipeline.
Uses raw asyncpg instead of SQLAlchemy ORM.
"""

import json
import os
import uuid
from typing import Optional

import asyncpg
import structlog
import uvicorn
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

from classifier import get_classifier
from clustering import get_clustering_service, get_embedding_service
from scoring import get_scorer
from transcription import get_transcription_service

logger = structlog.get_logger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
# asyncpg uses postgresql:// not postgresql+asyncpg://
_raw_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://anon_user:changeme_in_prod@postgres:5432/anon_signal")
DATABASE_URL = _raw_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/encrypted_uploads")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
AI_MODEL_VERSION = "v1.0-bart-whisper-minilm"

# ─── DB Pool ──────────────────────────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool

# ─── Encryption ───────────────────────────────────────────────────────────────
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
app = FastAPI(title="Anonymous Signal AI Service", docs_url=None, redoc_url=None)

class ProcessRequest(BaseModel):
    report_id: str

@app.get("/health")
async def health():
    return {"status": "operational", "service": "ai-processor"}

@app.post("/process/{report_id}")
async def process_report(report_id: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_ai_pipeline, report_id)
    return {"status": "queued", "report_id": report_id}

async def _run_ai_pipeline(report_id: str):
    logger.info("ai_pipeline_starting", report_id=report_id[:8])

    encryption = get_encryption_service()
    classifier = get_classifier()
    scorer = get_scorer()
    transcription_svc = get_transcription_service(WHISPER_MODEL)
    clustering_svc = get_clustering_service()
    embedding_svc = get_embedding_service()

    pool = await get_pool()

    async with pool.acquire() as conn:
        try:
            # 1. Load report
            row = await conn.fetchrow(
                "SELECT id, encrypted_content, has_audio, audio_ref, "
                "has_image, image_ref, user_category, status "
                "FROM reports WHERE id = $1 AND is_archived = false",
                report_id,
            )
            if not row:
                logger.error("report_not_found", report_id=report_id[:8])
                return
            if row["status"] == "analyzed":
                return

            await conn.execute("UPDATE reports SET status = 'processing' WHERE id = $1", report_id)

            # 2. Decrypt
            try:
                content_json = encryption.decrypt(row["encrypted_content"])
                content = json.loads(content_json)
                text_content = content.get("text", "")
            except Exception as e:
                logger.error("decrypt_failed", error=str(e))
                text_content = ""

            # 3. Transcribe audio
            transcription = ""
            transcription_confidence = 0.0
            if row["has_audio"] and row["audio_ref"]:
                transcription, transcription_confidence = (
                    await transcription_svc.transcribe_from_file_ref(
                        file_ref=row["audio_ref"],
                        upload_dir=UPLOAD_DIR,
                        encryption_service=encryption,
                    )
                )

            # 4. Combine text
            if text_content and transcription:
                combined_text = f"{text_content}\n{transcription}"
            elif text_content:
                combined_text = text_content
            elif transcription:
                combined_text = transcription
            else:
                combined_text = "No content available"

            # 5. Classify
            classification = await classifier.classify(combined_text)
            category = classification["category"]
            if classification["confidence"] < 0.4 and row["user_category"]:
                category = row["user_category"]

            # 6. Score severity
            severity_result = scorer.score(
                text=combined_text,
                category=category,
                classification_confidence=classification["confidence"],
            )

            # 7. Embedding
            embedding = embedding_svc.encode(combined_text)

            # 8. Cluster
            cluster_id = await clustering_svc.assign_cluster(
                report_id=report_id,
                text=combined_text,
                category=category,
                db=conn,
                alert_service=None,
            )

            # 9. Summary
            ai_summary = scorer.generate_ai_summary(
                text=combined_text,
                category=category,
                severity=severity_result["severity_score"],
                urgency=severity_result["urgency_level"],
                transcription=transcription if transcription else None,
            )

            # 10. Save analysis
            analysis_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO report_ai_analysis (
                    id, report_id, category, subcategory, confidence_score,
                    severity_score, urgency_level,
                    classification_reasoning, severity_reasoning,
                    embedding, cluster_id, model_version, analyzed_at,
                    transcription, transcription_confidence, ai_summary
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10, $11, $12, NOW(), $13, $14, $15
                )
                """,
                analysis_id, report_id, category,
                classification.get("subcategory"),
                classification["confidence"],
                severity_result["severity_score"],
                severity_result["urgency_level"],
                classification["reasoning"],
                severity_result["severity_reasoning"],
                embedding if embedding else None,
                cluster_id,
                AI_MODEL_VERSION,
                transcription or None,
                transcription_confidence or None,
                ai_summary,
            )

            await conn.execute(
                "UPDATE reports SET status = 'analyzed', processed_at = NOW() WHERE id = $1",
                report_id,
            )

            logger.info(
                "ai_pipeline_complete",
                report_id=report_id[:8],
                category=category,
                severity=severity_result["severity_score"],
            )

        except Exception as e:
            logger.error("ai_pipeline_failed", report_id=report_id[:8], error=str(e))
            try:
                await conn.execute(
                    "UPDATE reports SET status = 'pending' WHERE id = $1", report_id
                )
            except Exception:
                pass


if __name__ == "__main__":
    uvicorn.run("inference:app", host="0.0.0.0", port=8001, access_log=False, log_level="warning")