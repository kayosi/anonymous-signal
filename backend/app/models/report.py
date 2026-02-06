from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.core.database import Base

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    encrypted_content = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
