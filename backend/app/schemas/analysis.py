from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

class AnalysisTriggerRequest(BaseModel):
    reference_patent_numbers: Optional[List[str]] = None

class JobStatusDetail(BaseModel):
    reference_patent_id: UUID
    patent_number: str
    status: str
    error_message: Optional[str] = None

class AnalysisStatusResponse(BaseModel):
    percent_complete: int
    jobs: List[JobStatusDetail]
