from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

class SelectedClaimsRequest(BaseModel):
    claim_ids: List[UUID]

class ClaimElementSchema(BaseModel):
    id: Optional[UUID] = None
    element_id: str
    label: Optional[str] = None
    text: str
    weight: Decimal = Field(..., max_digits=5, decimal_places=2)
    comment: Optional[str] = None
    is_custom: Optional[bool] = False
    
    class Config:
        from_attributes = True

class CustomizeWeightsRequest(BaseModel):
    elements: List[ClaimElementSchema]

class ClaimResponse(BaseModel):
    id: UUID
    patent_id: UUID
    claim_number: int
    claim_text: str
    claim_type: str
    parent_claim_id: Optional[UUID] = None
    
    class Config:
        from_attributes = True
