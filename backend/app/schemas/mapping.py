from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

class MappingResponse(BaseModel):
    id: UUID
    claim_id: UUID
    element_id: UUID
    reference_patent_id: UUID
    classification: str
    analyst_classification: Optional[str] = None
    cited_passage: Optional[str] = None
    analyst_override: Optional[str] = None
    rationale: Optional[str] = None
    para_ref: Optional[str] = None
    fig_ref: Optional[str] = None
    
    class Config:
        from_attributes = True

class ScoreResponse(BaseModel):
    id: UUID
    reference_patent_id: UUID
    claim_id: UUID
    score: Decimal
    
    class Config:
        from_attributes = True

class MappingMatrixCell(BaseModel):
    element_id: str # e.g. 1A, 1B
    element_text: Optional[str] = None
    cited_passage: Optional[str] = None
    classification: str
    analyst_classification: Optional[str] = None

class MatrixRow(BaseModel):
    reference_patent_id: UUID
    patent_number: str
    title: Optional[str] = None
    score: float
    mappings: List[MappingMatrixCell]

class MatrixResponse(BaseModel):
    rows: List[MatrixRow]
