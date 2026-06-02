from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.database import get_db
from app.models.patent import Patent
from app.models.claim import Claim
from app.models.project import Project
from app.schemas.patent import PatentIngestRequest, PatentResponse
from app.services.patent_fetch import patent_fetch_service
from app.api.dependencies import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/ingest", response_model=PatentResponse, status_code=status.HTTP_201_CREATED)
async def ingest_patent(
    req: PatentIngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from app.core.logger import current_project_id
    import logging
    logger = logging.getLogger(__name__)
    
    # Set the context manually since the middleware doesn't catch project_id from the JSON payload
    current_project_id.set(str(req.project_id))
    
    logger.info(f"Step 1: Starting ingestion for patent {req.patent_number}")
    
    # Verify project ownership
    res_proj = await db.execute(
        select(Project).where(Project.id == req.project_id, Project.user_id == current_user.id)
    )


    
    project = res_proj.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    
    
    logger.info("Step 2: Project verified. Fetching patent data from external API...")
    # Fetch patent details (with retry logic — raises ValueError on total failure)
    try:
        patent_data = await patent_fetch_service.fetch_patent(req.patent_number)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch patent from external API: {e}"
        )
    
    logger.info("Step 3: Data fetched successfully. Storing patent record...")
    # Store patent record
    patent = Patent(
        project_id=req.project_id,
        patent_number=patent_data["patent_number"],
        title=patent_data["title"],
        abstract=patent_data["abstract"],
        assignee=patent_data["assignee"],
        is_reference=False,
        fetch_status="success",
        structured_summary=patent_data["structured_summary"]
    )

    

    db.add(patent)
    await db.flush() # Flush to get patent.id
    
    logger.info(f"Step 4: Creating {len(patent_data['claims'])} claim records...")
    # Create claims records
    for c in patent_data["claims"]:
        claim = Claim(
            patent_id=patent.id,
            claim_number=c["claim_number"],
            claim_text=c["claim_text"],
            claim_type=c["claim_type"]
        )
        
        db.add(claim)
    

    
    logger.info("Step 5: Updating project association...")
    # Update project association
    project.subject_patent_id = patent.id
    
    await db.commit()
    
    # Reload patent with claims populated
    res_pat = await db.execute(
        select(Patent)
        .options(selectinload(Patent.claims))
        .where(Patent.id == patent.id)
    )
    logger.info("Ingestion completed successfully.")
    return res_pat.scalars().first()

@router.get("/project/{project_id}", response_model=PatentResponse)
async def get_subject_patent(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify project
    res_proj = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = res_proj.scalars().first()
    if not project or not project.subject_patent_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject patent not found.")
        
    res_pat = await db.execute(
        select(Patent)
        .options(selectinload(Patent.claims))
        .where(Patent.id == project.subject_patent_id)
    )
    return res_pat.scalars().first()
