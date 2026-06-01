from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class ChartRowSchema(BaseModel):
    element_id: str
    claim_text: str
    cited_passage: str
    para_ref: Optional[str] = None
    fig_ref: Optional[str] = None
    rationale: str

class ClaimChartResponse(BaseModel):
    id: UUID
    project_id: UUID
    reference_patent_id: UUID
    claim_id: UUID
    chart_rows: List[ChartRowSchema]
    exported_at: Optional[datetime] = None
    export_format: Optional[str] = None
    
    class Config:
        from_attributes = True

class SaveChartEditsRequest(BaseModel):
    chart_rows: List[ChartRowSchema]
