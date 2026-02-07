from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class ReportAIAnalysis(Base):
    __tablename__ = "report_ai_analysis"

    id = Column(Integer, primary_key=True, index=True)

    report_id = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)

    ai_category = Column(String, nullable=False)
    urgency_score = Column(Float, nullable=False)
    severity_score = Column(Float, nullable=False)
    confidence_score = Column(Float, nullable=False)

    cluster_id = Column(String, nullable=True)

    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    analysis_type = Column(String, nullable=False)  # NLP / CV / AUDIO

    created_at = Column(DateTime(timezone=True), server_default=func.now())
