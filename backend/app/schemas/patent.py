from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from app.schemas.claim import ClaimResponse

class PatentIngestRequest(BaseModel):
    patent_number: str
    project_id: UUID

class PatentResponse(BaseModel):
    id: UUID
    project_id: UUID
    patent_number: str
    title: Optional[str] = None
    abstract: Optional[str] = None
    assignee: Optional[str] = None
    is_reference: bool
    fetch_status: str
    structured_summary: Optional[Dict[str, Any]] = None
    created_at: datetime
    claims: Optional[List[ClaimResponse]] = None
    
    class Config:
        from_attributes = True
