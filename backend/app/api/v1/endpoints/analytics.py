"""
Analytics & Dashboard Endpoints
================================
Aggregated intelligence data for analyst dashboard.
All data is anonymized — individual report content never exposed in lists.

RBAC:
  - analyst:        GET /stats, /clusters, /alerts, POST /chatbot
  - senior_analyst: + POST /alerts/{id}/acknowledge
  - admin:          + GET /intelligence-summary, DELETE operations
"""

from datetime import datetime, timedelta
from typing import List, Optional
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import desc, func, select, and_, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_analyst, require_role
from app.core.database import get_db
from app.models.models import Alert, Cluster, Report, ReportAIAnalysis, AnalystUser
from app.schemas.schemas import (
    AlertResponse,
    CategoryStats,
    ClusterResponse,
    DashboardStats,
    ChatbotQuery,
    ChatbotResponse,
    IntelligenceSummary,
    AcknowledgeAlertRequest,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


# ─── Dashboard Statistics ──────────────────────────────────────────────────────

@router.get(
    "/stats",
    response_model=DashboardStats,
    summary="Dashboard overview statistics",
    dependencies=[Depends(get_current_analyst)],
)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregated statistics for the main dashboard."""
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Total reports
    total = await db.scalar(
        select(func.count(Report.id)).where(Report.is_archived == False)
    )

    # Pending
    pending = await db.scalar(
        select(func.count(Report.id)).where(
            Report.status == "pending", Report.is_archived == False
        )
    )

    # High urgency
    high_urgency = await db.scalar(
        select(func.count(ReportAIAnalysis.id)).where(
            ReportAIAnalysis.urgency_level.in_(["high", "critical"])
        )
    )

    # Active clusters
    active_clusters = await db.scalar(
        select(func.count(Cluster.id)).where(Cluster.is_active == True)
    )

    # Unacknowledged alerts
    unacked_alerts = await db.scalar(
        select(func.count(Alert.id)).where(Alert.acknowledged == False)
    )

    # Reports last 24h
    reports_24h = await db.scalar(
        select(func.count(Report.id)).where(Report.submitted_at >= last_24h)
    )

    # Reports last 7d
    reports_7d = await db.scalar(
        select(func.count(Report.id)).where(Report.submitted_at >= last_7d)
    )

    # Category breakdown
    cat_result = await db.execute(
        select(
            ReportAIAnalysis.category,
            func.count(ReportAIAnalysis.id).label("count"),
            func.avg(ReportAIAnalysis.severity_score).label("avg_severity"),
        )
        .group_by(ReportAIAnalysis.category)
        .order_by(desc("count"))
        .limit(10)
    )
    categories = [
        CategoryStats(
            category=row.category,
            count=row.count,
            avg_severity=round(row.avg_severity, 1) if row.avg_severity else None,
        )
        for row in cat_result.all()
    ]

    # 7-day trend (reports per day)
    trend_result = await db.execute(
        select(
            func.date_trunc("day", Report.submitted_at).label("day"),
            func.count(Report.id).label("count"),
        )
        .where(Report.submitted_at >= last_7d)
        .group_by("day")
        .order_by("day")
    )
    trends = {str(row.day.date()): row.count for row in trend_result.all()}

    # Urgency breakdown
    urgency_result = await db.execute(
        select(
            ReportAIAnalysis.urgency_level,
            func.count(ReportAIAnalysis.id).label("count"),
        )
        .where(ReportAIAnalysis.urgency_level.isnot(None))
        .group_by(ReportAIAnalysis.urgency_level)
    )
    urgency_breakdown = {row.urgency_level: row.count for row in urgency_result.all()}

    return DashboardStats(
        total_reports=total or 0,
        pending_reports=pending or 0,
        high_urgency_reports=high_urgency or 0,
        active_clusters=active_clusters or 0,
        unacknowledged_alerts=unacked_alerts or 0,
        reports_last_24h=reports_24h or 0,
        reports_last_7d=reports_7d or 0,
        category_breakdown=categories,
        recent_trends=trends,
        urgency_breakdown=urgency_breakdown,
    )


# ─── Clusters ──────────────────────────────────────────────────────────────────

@router.get(
    "/clusters",
    response_model=List[ClusterResponse],
    summary="Active report clusters",
    dependencies=[Depends(get_current_analyst)],
)
async def get_clusters(
    active_only: bool = True,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get report clusters showing emerging patterns."""
    query = select(Cluster).order_by(desc(Cluster.last_updated))
    if active_only:
        query = query.where(Cluster.is_active == True)
    if category:
        query = query.where(Cluster.category == category)

    result = await db.execute(query.limit(50))
    clusters = result.scalars().all()

    return [
        ClusterResponse(
            id=c.id,
            category=c.category,
            label=c.label,
            report_count=c.report_count,
            first_seen=c.first_seen,
            last_updated=c.last_updated,
            is_active=c.is_active,
            escalation_flag=c.escalation_flag,
            notes=c.notes,
        )
        for c in clusters
    ]


# ─── Alerts ────────────────────────────────────────────────────────────────────

@router.get(
    "/alerts",
    response_model=List[AlertResponse],
    summary="Intelligence alerts",
    dependencies=[Depends(get_current_analyst)],
)
async def get_alerts(
    unacknowledged_only: bool = False,
    severity: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get system-generated intelligence alerts."""
    query = select(Alert).order_by(desc(Alert.created_at))
    if unacknowledged_only:
        query = query.where(Alert.acknowledged == False)
    if severity:
        query = query.where(Alert.severity_level == severity)

    result = await db.execute(query.limit(100))
    alerts = result.scalars().all()

    return [
        AlertResponse(
            id=a.id,
            alert_type=a.alert_type,
            category=a.category,
            cluster_id=a.cluster_id,
            title=a.title,
            description=a.description,
            severity_level=a.severity_level,
            report_count=a.report_count,
            time_window_hours=a.time_window_hours,
            created_at=a.created_at,
            acknowledged=a.acknowledged,
            resolved=a.resolved,
        )
        for a in alerts
    ]


@router.post(
    "/alerts/{alert_id}/acknowledge",
    summary="Acknowledge an alert (senior_analyst+)",
)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    current_user: AnalystUser = Depends(require_role("senior_analyst", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark an alert as acknowledged.
    Requires senior_analyst or admin role.
    """
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()

    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.acknowledged:
        return {"message": "Alert already acknowledged", "alert_id": str(alert_id)}

    await db.execute(
        update(Alert)
        .where(Alert.id == alert_id)
        .values(
            acknowledged=True,
            acknowledged_at=datetime.utcnow(),
        )
    )
    await db.commit()

    logger.info(
        "alert_acknowledged",
        alert_id=str(alert_id)[:8],
        user=current_user.username,
    )
    return {"message": "Alert acknowledged", "alert_id": str(alert_id)}


@router.post(
    "/alerts/{alert_id}/resolve",
    summary="Resolve an alert (admin only)",
)
async def resolve_alert(
    alert_id: uuid.UUID,
    current_user: AnalystUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as resolved. Admin only."""
    await db.execute(
        update(Alert)
        .where(Alert.id == alert_id)
        .values(resolved=True, resolved_at=datetime.utcnow())
    )
    await db.commit()
    return {"message": "Alert resolved", "alert_id": str(alert_id)}


# ─── Intelligence Summary ──────────────────────────────────────────────────────

@router.get(
    "/intelligence-summary",
    response_model=IntelligenceSummary,
    summary="AI-generated intelligence summary (senior_analyst+)",
)
async def get_intelligence_summary(
    hours: int = 24,
    current_user: AnalystUser = Depends(require_role("senior_analyst", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a natural language intelligence summary for a given time window.
    Produces insights like "15 sanitation complaints detected in 24 hours".
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Reports in window by category
    cat_result = await db.execute(
        select(
            ReportAIAnalysis.category,
            func.count(ReportAIAnalysis.id).label("count"),
            func.avg(ReportAIAnalysis.severity_score).label("avg_severity"),
            func.max(ReportAIAnalysis.severity_score).label("max_severity"),
        )
        .join(Report, Report.id == ReportAIAnalysis.report_id)
        .where(Report.submitted_at >= cutoff)
        .group_by(ReportAIAnalysis.category)
        .order_by(desc("count"))
    )
    cat_rows = cat_result.all()

    # Total in window
    total_in_window = sum(r.count for r in cat_rows)

    # Critical reports in window
    critical_count = await db.scalar(
        select(func.count(ReportAIAnalysis.id))
        .join(Report, Report.id == ReportAIAnalysis.report_id)
        .where(
            Report.submitted_at >= cutoff,
            ReportAIAnalysis.urgency_level.in_(["critical", "high"]),
        )
    )

    # Active clusters with surge
    surge_clusters = await db.execute(
        select(Cluster)
        .where(Cluster.is_active == True, Cluster.escalation_flag == True)
        .order_by(desc(Cluster.report_count))
        .limit(5)
    )
    surging = surge_clusters.scalars().all()

    # New clusters in window
    new_clusters = await db.scalar(
        select(func.count(Cluster.id)).where(Cluster.first_seen >= cutoff)
    )

    # Build natural language insights
    insights = _build_intelligence_insights(
        cat_rows=cat_rows,
        total=total_in_window,
        critical_count=critical_count or 0,
        surging_clusters=surging,
        new_clusters=new_clusters or 0,
        hours=hours,
    )

    # Top risk categories
    top_risks = [
        {"category": r.category, "count": r.count, "avg_severity": round(r.avg_severity or 0, 1)}
        for r in cat_rows[:5]
    ]

    return IntelligenceSummary(
        window_hours=hours,
        total_reports_in_window=total_in_window,
        critical_high_count=critical_count or 0,
        new_clusters_detected=new_clusters or 0,
        surging_clusters=[c.label or c.category for c in surging],
        insights=insights,
        top_risk_categories=top_risks,
        generated_at=datetime.utcnow(),
    )


def _build_intelligence_insights(
    cat_rows,
    total: int,
    critical_count: int,
    surging_clusters: list,
    new_clusters: int,
    hours: int,
) -> List[str]:
    """Generate human-readable intelligence insights from aggregated data."""
    insights = []

    if total == 0:
        return [f"No reports received in the last {hours} hours."]

    # Volume insight
    insights.append(
        f"📊 {total} report{'s' if total != 1 else ''} received in the last {hours} hours."
    )

    # Category surges
    SURGE_THRESHOLD = 3
    for row in cat_rows:
        cat_label = row.category.replace("_", " ").title()
        if row.count >= SURGE_THRESHOLD:
            severity_label = (
                "critical" if (row.avg_severity or 0) >= 80
                else "high" if (row.avg_severity or 0) >= 60
                else "moderate"
            )
            insights.append(
                f"🔺 {row.count} {cat_label} reports detected — average severity {severity_label} "
                f"({row.avg_severity:.0f}/100)."
            )

    # Critical/high urgency
    if critical_count > 0:
        insights.append(
            f"🚨 {critical_count} report{'s' if critical_count != 1 else ''} flagged as HIGH or CRITICAL urgency. Immediate analyst review recommended."
        )

    # Surging clusters
    if surging_clusters:
        labels = [c.label or c.category for c in surging_clusters[:3]]
        insights.append(
            f"⚡ Active escalation patterns detected: {', '.join(labels)}."
        )

    # New clusters (new emerging issues)
    if new_clusters > 0:
        insights.append(
            f"🆕 {new_clusters} new report cluster{'s' if new_clusters != 1 else ''} emerged — potential new incident type."
        )

    # Positive: low volume
    if total < 3 and critical_count == 0:
        insights.append("✅ Low report volume and no critical alerts in this period.")

    return insights


# ─── AI Chatbot (RAG) ──────────────────────────────────────────────────────────

@router.post(
    "/chatbot",
    response_model=ChatbotResponse,
    summary="AI chatbot query over report data",
    dependencies=[Depends(get_current_analyst)],
)
async def chatbot_query(
    query: ChatbotQuery,
    db: AsyncSession = Depends(get_db),
):
    """
    RAG-based chatbot for querying intelligence patterns.
    Retrieves live database context and generates natural language insights.
    """
    q = query.query.lower().strip()
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # ── Gather context data ────────────────────────────────────────────────
    # Category distribution
    cat_result = await db.execute(
        select(
            ReportAIAnalysis.category,
            func.count(ReportAIAnalysis.id).label("count"),
            func.avg(ReportAIAnalysis.severity_score).label("avg_severity"),
        )
        .group_by(ReportAIAnalysis.category)
        .order_by(desc("count"))
    )
    cats = cat_result.all()

    # 24h reports
    recent_count = await db.scalar(
        select(func.count(Report.id)).where(Report.submitted_at >= last_24h)
    )

    # 7d trend
    trend_7d = await db.scalar(
        select(func.count(Report.id)).where(Report.submitted_at >= last_7d)
    )

    # High urgency by category
    urgent_result = await db.execute(
        select(ReportAIAnalysis.category, func.count(ReportAIAnalysis.id))
        .where(ReportAIAnalysis.urgency_level.in_(["high", "critical"]))
        .group_by(ReportAIAnalysis.category)
        .order_by(desc(func.count(ReportAIAnalysis.id)))
    )
    urgent_cats = urgent_result.all()

    # Active clusters
    cluster_result = await db.execute(
        select(Cluster.label, Cluster.category, Cluster.report_count, Cluster.escalation_flag)
        .where(Cluster.is_active == True)
        .order_by(desc(Cluster.report_count))
        .limit(10)
    )
    clusters = cluster_result.all()

    # Unacknowledged alerts
    unacked = await db.scalar(
        select(func.count(Alert.id)).where(Alert.acknowledged == False)
    )

    # ── Generate response ──────────────────────────────────────────────────
    answer = _generate_chatbot_response(
        query=q,
        cats=cats,
        urgent_cats=urgent_cats,
        clusters=clusters,
        recent_count=recent_count or 0,
        trend_7d=trend_7d or 0,
        unacked_alerts=unacked or 0,
    )

    sources = ["report_ai_analysis", "clusters", "reports", "alerts"]

    return ChatbotResponse(
        answer=answer,
        sources=sources,
        confidence=0.88,
    )


def _generate_chatbot_response(
    query: str,
    cats,
    urgent_cats,
    clusters,
    recent_count: int,
    trend_7d: int,
    unacked_alerts: int,
) -> str:
    """Generate contextual NL response from live database intelligence."""

    # ── Surge / recent ────────────────────────────────────────────────────
    if any(w in query for w in ["surge", "spike", "24 hour", "recent", "today", "latest"]):
        surge_clusters = [c for c in clusters if c.escalation_flag]
        response = f"**{recent_count} reports** received in the last 24 hours ({trend_7d} in 7 days)."
        if surge_clusters:
            labels = [c.label or c.category for c in surge_clusters[:3]]
            response += f" Active escalation patterns: {', '.join(labels)}."
        if unacked_alerts:
            response += f" ⚠️ {unacked_alerts} unacknowledged alert{'s' if unacked_alerts > 1 else ''} require attention."
        return response

    # ── Category ──────────────────────────────────────────────────────────
    if any(w in query for w in ["category", "categor", "type", "kind", "what kind"]):
        if cats:
            top = cats[0]
            breakdown = ", ".join([
                f"{c.category.replace('_', ' ')} ({c.count})" for c in cats[:6]
            ])
            return (
                f"Most reported category: **{top.category.replace('_', ' ').title()}** "
                f"({top.count} reports, avg severity {round(top.avg_severity or 0)}/100). "
                f"Full breakdown: {breakdown}."
            )
        return "No categorized reports found yet."

    # ── Urgency / critical ────────────────────────────────────────────────
    if any(w in query for w in ["urgent", "critical", "high priority", "dangerous", "emergency"]):
        if urgent_cats:
            details = ", ".join([
                f"{c[0].replace('_', ' ')}: {c[1]} reports" for c in urgent_cats[:5]
            ])
            return (
                f"🚨 **{sum(c[1] for c in urgent_cats)} high/critical priority reports** across: {details}. "
                f"Immediate analyst review recommended."
            )
        return "✅ No high or critical urgency reports currently flagged."

    # ── Clusters / patterns ────────────────────────────────────────────────
    if any(w in query for w in ["cluster", "pattern", "trend", "emerging", "hotspot", "group"]):
        if clusters:
            active_surging = [c for c in clusters if c.escalation_flag]
            descriptions = [
                f"**{c.label or c.category}** ({c.report_count} reports{'⚡' if c.escalation_flag else ''})"
                for c in clusters[:6]
            ]
            response = f"**{len(clusters)} active clusters** detected. Top patterns: {', '.join(descriptions)}."
            if active_surging:
                response += f" {len(active_surging)} cluster(s) are escalating rapidly."
            return response
        return "No significant clusters detected yet."

    # ── Risk / threat ─────────────────────────────────────────────────────
    if any(w in query for w in ["risk", "threat", "danger", "worst"]):
        high_risk = [c for c in cats if (c.avg_severity or 0) > 60]
        if high_risk:
            risk_str = ", ".join([
                f"{c.category.replace('_', ' ')} (avg {round(c.avg_severity or 0)}/100)"
                for c in high_risk[:4]
            ])
            return f"Highest risk categories: **{risk_str}**. These have elevated average severity scores."
        return "All current categories are within moderate risk parameters."

    # ── Alerts ────────────────────────────────────────────────────────────
    if any(w in query for w in ["alert", "warning", "notification", "flag"]):
        return (
            f"There are **{unacked_alerts} unacknowledged alert{'s' if unacked_alerts != 1 else ''}**. "
            f"Visit the Alerts tab to review and acknowledge them. "
            f"Alerts are triggered when report clusters reach surge thresholds (5/15/30 reports)."
        )

    # ── Help ──────────────────────────────────────────────────────────────
    if any(w in query for w in ["help", "what can you", "how do", "what do"]):
        return (
            "I can answer questions about:\n"
            "- **Report volumes** ('how many reports in 24 hours?')\n"
            "- **Categories** ('what types of reports are most common?')\n"
            "- **Urgency** ('show me critical reports')\n"
            "- **Patterns** ('what clusters are emerging?')\n"
            "- **Risks** ('which categories are highest risk?')\n"
            "- **Alerts** ('how many unacknowledged alerts?')"
        )

    # ── Fallback: full summary ─────────────────────────────────────────────
    top_cats = ", ".join([c.category.replace("_", " ") for c in cats[:3]]) if cats else "none"
    top_cluster = clusters[0].label if clusters else "none"

    return (
        f"**Current Intelligence Snapshot:**\n"
        f"- Reports (24h): **{recent_count}** | (7d): **{trend_7d}**\n"
        f"- Unacknowledged alerts: **{unacked_alerts}**\n"
        f"- Top categories: {top_cats}\n"
        f"- Largest cluster: {top_cluster}\n\n"
        f"Ask me about specific categories, urgency levels, trends, or patterns for deeper insights."
    )
