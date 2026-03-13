"""
Database Models
===============
SQLAlchemy ORM models matching the SQL schema.
All models designed with privacy-by-default.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, ARRAY, CheckConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Report(Base):
    """
    Anonymous report submission.
    PRIVACY: No PII columns. Content encrypted at application layer.
    """
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Encrypted payload — decryptable only with ENCRYPTION_KEY
    encrypted_content = Column(Text, nullable=False)

    # Media presence flags
    has_audio = Column(Boolean, default=False)
    has_image = Column(Boolean, default=False)
    audio_ref = Column(Text, nullable=True)    # Anonymous encrypted filename
    image_ref = Column(Text, nullable=True)    # Anonymous encrypted filename

    # User-selected category (pre-AI classification)
    user_category = Column(String(64), nullable=True)

    # Processing pipeline status
    status = Column(
        String(32),
        default="pending",
        nullable=False,
    )

    # Timestamps
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Soft delete
    is_archived = Column(Boolean, default=False)

    # Anonymous tracking code (bcrypt hashed) — given to reporter once on submission
    tracking_code_hash = Column(Text, nullable=True)

    # Relationships
    ai_analyses = relationship("ReportAIAnalysis", back_populates="report", cascade="all, delete-orphan")
    messages = relationship("ReportMessage", back_populates="report", cascade="all, delete-orphan", order_by="ReportMessage.created_at")


class ReportAIAnalysis(Base):
    """AI analysis results for a report. Multiple per report supported."""
    __tablename__ = "report_ai_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)

    # Classification
    category = Column(String(64), nullable=False)
    subcategory = Column(String(128), nullable=True)
    confidence_score = Column(Float, nullable=True)

    # Severity
    severity_score = Column(Integer, nullable=True)
    urgency_level = Column(String(16), nullable=True)

    # Explainability
    classification_reasoning = Column(Text, nullable=True)
    severity_reasoning = Column(Text, nullable=True)

    # Clustering
    embedding = Column(ARRAY(Float), nullable=True)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True)

    # Model metadata
    model_version = Column(String(64), nullable=True)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Transcription (for audio reports)
    transcription = Column(Text, nullable=True)
    transcription_confidence = Column(Float, nullable=True)

    # AI summary
    ai_summary = Column(Text, nullable=True)

    # Relationships
    report = relationship("Report", back_populates="ai_analyses")
    cluster = relationship("Cluster", back_populates="analyses")


class Cluster(Base):
    """Groups of similar reports detected by clustering."""
    __tablename__ = "clusters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(64), nullable=True)
    label = Column(Text, nullable=True)
    centroid_embedding = Column(ARRAY(Float), nullable=True)
    report_count = Column(Integer, default=0)
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    escalation_flag = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    # Relationships
    analyses = relationship("ReportAIAnalysis", back_populates="cluster")
    alerts = relationship("Alert", back_populates="cluster")


class Alert(Base):
    """System-generated intelligence alerts."""
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_type = Column(String(64), nullable=False)
    category = Column(String(64), nullable=True)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("clusters.id"), nullable=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    severity_level = Column(String(16), default="medium")
    report_count = Column(Integer, nullable=True)
    time_window_hours = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship
    cluster = relationship("Cluster", back_populates="alerts")


class ReportMessage(Base):
    """
    Anonymous chat messages between analysts and reporters.
    Reporter identified only by their tracking code — no PII stored.
    """
    __tablename__ = "report_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    sender = Column(String(16), nullable=False)  # 'analyst' or 'reporter'
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_by_analyst = Column(Boolean, default=False)
    read_by_reporter = Column(Boolean, default=False)

    # Relationships
    report = relationship("Report", back_populates="messages")


class AnalystUser(Base):
    """Dashboard analyst accounts — NOT linked to report submitters."""
    __tablename__ = "analyst_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(32), default="analyst")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)