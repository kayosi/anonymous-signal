from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models.report import Base, Report
from app.schemas.report import ReportCreate
from app.core.security import encrypt_report

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Anonymous Signal API")

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/report")
def create_report(report: ReportCreate, db: Session = Depends(get_db)):
    try:
        encrypted_content = encrypt_report(report.content)
        db_report = Report(category=report.category, encrypted_content=encrypted_content)
        db.add(db_report)
        db.commit()
        db.refresh(db_report)
        return {"status": "success", "report_id": db_report.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
from app.core.security import decrypt_report

"""
# DECRYPT TEST
@app.get("/debug/{report_id}")
def debug_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    return {"decrypted": decrypt_report(report.encrypted_content)}
"""

