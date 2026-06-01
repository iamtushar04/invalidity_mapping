from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.claim import Claim
from app.models.mapping import ClaimElement
from app.models.project import Project
from app.schemas.claim import SelectedClaimsRequest, ClaimElementSchema, CustomizeWeightsRequest
from app.services.claim_parser import claim_parser_service
from app.api.dependencies import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/project/{project_id}/selected-claims", response_model=List[UUID])
async def save_selected_claims(
    project_id: UUID,
    req: SelectedClaimsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project
    res_proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = res_proj.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
        
    project.selected_claim_ids = req.claim_ids
    await db.commit()
    return project.selected_claim_ids

@router.post("/{claim_id}/parse-elements", response_model=List[ClaimElementSchema])
async def parse_claim_elements(
    claim_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Check existing elements
    res_el = await db.execute(select(ClaimElement).where(ClaimElement.claim_id == claim_id))
    existing_elements = res_el.scalars().all()
    if existing_elements:
        return existing_elements
        
    # Fetch claim text
    res_cl = await db.execute(select(Claim).where(Claim.id == claim_id))
    claim = res_cl.scalars().first()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found.")
        
    # Segment elements
    elements_data = await claim_parser_service.segment_claim(claim.claim_text, claim.claim_number)
    
    # Store records
    elements = []
    for el in elements_data:
        weight = el["weight"]
        if weight >= 30:
            priority = "Critical"
        elif weight >= 20:
            priority = "High"
        elif weight >= 10:
            priority = "Medium"
        else:
            priority = "Low"
            
        label_with_priority = f"{el['label']}:::{priority}"
        
        element = ClaimElement(
            claim_id=claim_id,
            element_id=el["element_id"],
            label=label_with_priority,
            text=el["text"],
            weight=weight
        )
        db.add(element)
        elements.append(element)
        
    await db.commit()
    return elements

@router.put("/{claim_id}/elements", response_model=List[ClaimElementSchema])
async def update_claim_elements_weights(
    claim_id: UUID,
    req: CustomizeWeightsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
# Removed strict sum validation – weights are independent and individually clamped in the service layer.
        
    # Clear existing elements
    await db.execute(delete(ClaimElement).where(ClaimElement.claim_id == claim_id))
    
    # Add customized elements
    elements = []
    for el in req.elements:
        weight = el.weight
        if weight >= 30:
            priority = "Critical"
        elif weight >= 20:
            priority = "High"
        elif weight >= 10:
            priority = "Medium"
        else:
            priority = "Low"
            
        # Guard against a missing label (None). Use empty string as base.
        base_label = el.label.split(":::")[0] if el.label and ":::" in el.label else (el.label or "")
        label_with_priority = f"{base_label}:::{priority}"
        
        element = ClaimElement(
            claim_id=claim_id,
            element_id=el.element_id,
            label=label_with_priority,
            text=el.text,
            weight=weight,
            comment=el.comment,
            is_custom=el.is_custom
        )
        db.add(element)
        elements.append(element)
        
    await db.commit()
    return elements
