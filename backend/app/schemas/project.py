from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class ProjectBase(BaseModel):
    name: str

class ProjectCreate(ProjectBase):
    pass

class ProjectResponse(ProjectBase):
    id: UUID
    user_id: UUID
    subject_patent_id: Optional[UUID] = None
    selected_claim_ids: List[UUID] = []
    created_at: datetime
    
    class Config:
        from_attributes = True
