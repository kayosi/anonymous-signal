"""
Intelligence Scheduler
=======================
Background task that periodically:
  1. Scans for category surges (N reports of same type in X hours)
  2. Updates cluster escalation flags
  3. Generates intelligence summary alerts
  4. Retries pending reports stuck in processing

Runs as a background task within the FastAPI app (no separate Celery needed).

PRIVACY: This task only reads aggregated, anonymized data.
It never accesses decrypted report content.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Surge thresholds: (count_in_24h, severity_label)
SURGE_RULES = [
    (30, "critical"),
    (15, "high"),
    (5,  "medium"),
]

# How often to run the scheduler (seconds)
SCHEDULER_INTERVAL_SECONDS = 300  # Every 5 minutes


async def run_intelligence_scheduler(database_url: str):
    """
    Main scheduler loop. Runs indefinitely as a background asyncio task.
    Start this in the FastAPI startup event.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select, func, update, desc

    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    logger.info("intelligence_scheduler_started", interval=SCHEDULER_INTERVAL_SECONDS)

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await _check_category_surges(db)
                await _update_cluster_escalations(db)
                await _retry_stuck_reports(db)
                await _auto_delete_expired_spam(db)
                await db.commit()
            logger.info("intelligence_scheduler_cycle_complete")
        except Exception as e:
            logger.error("scheduler_cycle_failed", error=str(e))

        await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)


async def _check_category_surges(db):
    """
    Detect if any category has had a surge in the last 24 hours.
    Creates an alert if threshold is crossed and no recent alert exists for that category.
    """
    from sqlalchemy import select, func, text, desc
    from app.models.models import Report, ReportAIAnalysis, Alert

    cutoff_24h = datetime.utcnow() - timedelta(hours=24)

    # Count reports per category in last 24h
    result = await db.execute(
        select(
            ReportAIAnalysis.category,
            func.count(ReportAIAnalysis.id).label("count"),
        )
        .join(Report, Report.id == ReportAIAnalysis.report_id)
        .where(Report.submitted_at >= cutoff_24h)
        .group_by(ReportAIAnalysis.category)
        .having(func.count(ReportAIAnalysis.id) >= 5)
        .order_by(desc("count"))
    )
    surges = result.all()

    for surge in surges:
        category = surge.category
        count = surge.count

        # Determine severity
        severity = "medium"
        for threshold, sev in SURGE_RULES:
            if count >= threshold:
                severity = sev
                break

        # Check if we already alerted for this category recently (last 6h)
        recent_alert_cutoff = datetime.utcnow() - timedelta(hours=6)
        existing = await db.scalar(
            select(func.count(Alert.id)).where(
                Alert.category == category,
                Alert.alert_type == "category_surge",
                Alert.created_at >= recent_alert_cutoff,
            )
        )

        if existing:
            continue  # Already alerted recently

        # Create surge alert
        alert = Alert(
            id=uuid.uuid4(),
            alert_type="category_surge",
            category=category,
            title=f"Category Surge: {category.replace('_', ' ').title()}",
            description=(
                f"{count} {category.replace('_', ' ')} reports detected in the last 24 hours. "
                f"This represents a significant spike requiring analyst attention."
            ),
            severity_level=severity,
            report_count=count,
            time_window_hours=24,
        )
        db.add(alert)

        logger.warning(
            "category_surge_alert_created",
            category=category,
            count=count,
            severity=severity,
        )


async def _update_cluster_escalations(db):
    """
    Update escalation_flag on clusters that are growing rapidly.
    A cluster is escalating if it gained 5+ reports in the last hour.
    """
    from sqlalchemy import select, func, update
    from app.models.models import Cluster, ReportAIAnalysis

    cutoff_1h = datetime.utcnow() - timedelta(hours=1)

    # Find clusters with rapid growth
    result = await db.execute(
        select(
            ReportAIAnalysis.cluster_id,
            func.count(ReportAIAnalysis.id).label("recent_count"),
        )
        .where(
            ReportAIAnalysis.cluster_id.isnot(None),
            ReportAIAnalysis.analyzed_at >= cutoff_1h,
        )
        .group_by(ReportAIAnalysis.cluster_id)
        .having(func.count(ReportAIAnalysis.id) >= 5)
    )
    escalating = result.all()

    escalating_ids = [row.cluster_id for row in escalating]

    # Set escalation flag on rapidly growing clusters
    if escalating_ids:
        await db.execute(
            update(Cluster)
            .where(Cluster.id.in_(escalating_ids))
            .values(escalation_flag=True)
        )
        logger.info("cluster_escalations_updated", count=len(escalating_ids))

    # Clear escalation flag on quiet clusters (no new reports in 2h)
    cutoff_2h = datetime.utcnow() - timedelta(hours=2)
    quiet_result = await db.execute(
        select(Cluster.id)
        .where(
            Cluster.escalation_flag == True,
            Cluster.last_updated < cutoff_2h,
        )
    )
    quiet_ids = [row.id for row in quiet_result.all()]

    if quiet_ids:
        await db.execute(
            update(Cluster)
            .where(Cluster.id.in_(quiet_ids))
            .values(escalation_flag=False)
        )


async def _retry_stuck_reports(db):
    """
    Reset reports stuck in 'processing' status for more than 10 minutes.
    This handles AI service crashes gracefully.
    """
    from sqlalchemy import select, update
    from app.models.models import Report
    import httpx
    import os

    stuck_cutoff = datetime.utcnow() - timedelta(minutes=10)

    result = await db.execute(
        select(Report.id).where(
            Report.status == "processing",
            Report.submitted_at < stuck_cutoff,
        ).limit(10)
    )
    stuck_ids = [row.id for row in result.all()]

    if stuck_ids:
        # Reset to pending for retry
        await db.execute(
            update(Report)
            .where(Report.id.in_(stuck_ids))
            .values(status="pending")
        )
        logger.warning("stuck_reports_reset", count=len(stuck_ids))

        # Re-trigger AI processing
        ai_url = os.getenv("AI_SERVICE_URL", "http://ai-service:8001")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                for report_id in stuck_ids:
                    await client.post(f"{ai_url}/process/{report_id}")
        except Exception as e:
            logger.error("retry_trigger_failed", error=str(e))

async def _auto_delete_expired_spam(db):
    """
    Archive spam reports whose 30-day auto-delete window has passed.
    Runs every scheduler cycle (~5 minutes).
    """
    from sqlalchemy import update
    from app.models.models import Report

    now = datetime.utcnow()
    result = await db.execute(
        update(Report)
        .where(
            Report.status == "flagged",
            Report.is_archived == False,
            Report.spam_deleted_at <= now,
            Report.spam_deleted_at.isnot(None),
        )
        .values(is_archived=True)
        .returning(Report.id)
    )
    deleted = result.fetchall()
    if deleted:
        logger.info("spam_auto_deleted", count=len(deleted))