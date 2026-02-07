from pydantic import BaseModel
from typing import Optional

class ReportCreate(BaseModel):
    category: str
    content: str
    attachment: Optional[str] = None  # base64 string for photo/audio