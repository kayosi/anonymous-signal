from pydantic import BaseModel

class ReportCreate(BaseModel):
    category: str
    content: str
