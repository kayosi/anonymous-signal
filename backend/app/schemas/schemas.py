"""
Pydantic Schemas
================
Request and response schemas with strict validation.
PRIVACY: Response schemas never include PII or identifying fields.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ─── Report Submission ─────────────────────────────────────────────────────

VALID_CATEGORIES = [
    "public_safety",
    "infrastructure",
    "crime_signals",
    "health_sanitation",
    "environmental_risks",
    "service_delivery",
    "terrorism",
    "corruption",
    "other",
]


class ReportSubmitRequest(BaseModel):
    """Schema for anonymous report submission."""
    text_content: Optional[str] = Field(
        None, max_length=5000, description="Text description of the report"
    )
    user_category: Optional[str] = Field(None, description="User-selected category")
    location_hint: Optional[str] = Field(
        None,
        max_length=200,
        description="General area hint (e.g., 'Northern District') — no precise GPS",
    )

    @field_validator("user_category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        if v and v not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {VALID_CATEGORIES}")
        return v

    @field_validator("text_content")
    @classmethod
    def validate_content(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
        return v


class ReportSubmitResponse(BaseModel):
    """Response after anonymous report submission."""
    report_id: uuid.UUID
    status: str
    message: str
    # PRIVACY: No timestamps, no tracking IDs


# ─── Analysis Schemas ──────────────────────────────────────────────────────

class AIAnalysisResponse(BaseModel):
    """AI analysis result."""
    id: uuid.UUID
    report_id: uuid.UUID
    category: str
    subcategory: Optional[str]
    confidence_score: Optional[float]
    severity_score: Optional[int]
    urgency_level: Optional[str]
    classification_reasoning: Optional[str]
    severity_reasoning: Optional[str]
    transcription: Optional[str]
    transcription_confidence: Optional[float]
    ai_summary: Optional[str]
    cluster_id: Optional[uuid.UUID]
    analyzed_at: datetime
    model_version: Optional[str]

    class Config:
        from_attributes = True


# ─── Report Detail (Dashboard) ─────────────────────────────────────────────

class ReportDetailResponse(BaseModel):
    """Full report detail for analyst dashboard."""
    id: uuid.UUID
    status: str
    user_category: Optional[str]
    submitted_at: datetime
    processed_at: Optional[datetime]
    has_audio: bool
    has_image: bool
    decrypted_text: Optional[str] = None
    ai_analyses: List[AIAnalysisResponse] = []

    class Config:
        from_attributes = True


class ReportListItem(BaseModel):
    """Lightweight report item for list view."""
    id: uuid.UUID
    status: str
    user_category: Optional[str]
    submitted_at: datetime
    urgency_level: Optional[str] = None
    severity_score: Optional[int] = None
    category: Optional[str] = None

    class Config:
        from_attributes = True


class PaginatedReports(BaseModel):
    items: List[ReportListItem]
    total: int
    page: int
    page_size: int


# ─── Cluster Schemas ───────────────────────────────────────────────────────

class ClusterResponse(BaseModel):
    id: uuid.UUID
    category: Optional[str]
    label: Optional[str]
    report_count: int
    first_seen: datetime
    last_updated: datetime
    is_active: bool
    escalation_flag: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


# ─── Alert Schemas ─────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: uuid.UUID
    alert_type: str
    category: Optional[str]
    cluster_id: Optional[uuid.UUID]
    title: str
    description: str
    severity_level: str
    report_count: Optional[int]
    time_window_hours: Optional[int]
    created_at: datetime
    acknowledged: bool
    resolved: bool

    class Config:
        from_attributes = True


class AcknowledgeAlertRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=500)


# ─── Statistics ────────────────────────────────────────────────────────────

class CategoryStats(BaseModel):
    category: str
    count: int
    avg_severity: Optional[float]


class DashboardStats(BaseModel):
    total_reports: int
    pending_reports: int
    high_urgency_reports: int
    active_clusters: int
    unacknowledged_alerts: int
    reports_last_24h: int
    reports_last_7d: int
    category_breakdown: List[CategoryStats]
    recent_trends: Dict[str, Any]
    urgency_breakdown: Dict[str, int] = {}


# ─── Intelligence Summary ──────────────────────────────────────────────────

class IntelligenceSummary(BaseModel):
    """AI-generated intelligence summary for a time window."""
    window_hours: int
    total_reports_in_window: int
    critical_high_count: int
    new_clusters_detected: int
    surging_clusters: List[str]
    insights: List[str]
    top_risk_categories: List[Dict[str, Any]]
    generated_at: datetime


# ─── Chatbot ───────────────────────────────────────────────────────────────

class ChatbotQuery(BaseModel):
    query: str = Field(..., max_length=500, description="Natural language query about report data")
    context: Optional[str] = Field(None, description="Previous conversation context")


class ChatbotResponse(BaseModel):
    answer: str
    sources: Optional[List[str]] = None
    confidence: Optional[float] = None


# ─── Auth ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ─── Tracking Code / Reporter Chat Schemas ───────────────────────────────────

class ReportSubmitResponse(BaseModel):
    """Returned once on submission — tracking_code shown only here, never again."""
    report_id: uuid.UUID
    status: str
    message: str
    tracking_code: str  # e.g. KE-7X4M-2R9P — shown once, not stored in plain text


class ReportMessageOut(BaseModel):
    id: uuid.UUID
    sender: str  # 'analyst' or 'reporter'
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class ReportTrackResponse(BaseModel):
    """Reporter view of their report status via tracking code."""
    report_id: uuid.UUID
    status: str
    user_category: Optional[str] = None
    submitted_at: datetime
    urgency_level: Optional[str] = None
    category: Optional[str] = None
    messages: List[ReportMessageOut] = []
    unread_from_analyst: int = 0


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class AnalystSendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)