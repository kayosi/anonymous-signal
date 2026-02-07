from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models.report import Base, Report
from app.schemas.report import ReportCreate
from app.core.security import encrypt_report, encrypt_attachment

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
    """
    NOTE:
    This endpoint intentionally does not read or store
    request headers, IP addresses, or client metadata.
    Fully anonymous by design.
    """
    try:
        encrypted_content = encrypt_report(report.content)
        encrypted_attachment = None
        if report.attachment:
            encrypted_attachment = encrypt_attachment(report.attachment)
        db_report = Report(
            category=report.category,
            encrypted_content=encrypted_content,
            encrypted_attachment=encrypted_attachment
        )
        db.add(db_report)
        db.commit()
        db.refresh(db_report)
        return {"status": "success", "report_id": db_report.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

"""
# DECRYPT TEST
@app.get("/debug/{report_id}")
def debug_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    return {"decrypted": decrypt_report(report.encrypted_content)}
"""

