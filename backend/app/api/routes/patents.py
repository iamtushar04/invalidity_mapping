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

from fastapi import BackgroundTasks
from app.tasks.subject_ingestion import background_ingest_subject_patent
import json

@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_patent(
    req: PatentIngestRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from app.core.logger import current_project_id
    import logging
    logger = logging.getLogger(__name__)
    
    current_project_id.set(str(req.project_id))
    logger.info(f"Queueing background ingestion for patent {req.patent_number}")
    
    # Verify project ownership
    res_proj = await db.execute(
        select(Project).where(Project.id == req.project_id, Project.user_id == current_user.id)
    )
    project = res_proj.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    
    from app.services.redis_service import set_subject_ingestion_status
    initial_status = json.dumps({"status": "pending", "message": "Queued for ingestion...", "progress": 0})
    await set_subject_ingestion_status(str(req.project_id), initial_status)
    
    background_tasks.add_task(
        background_ingest_subject_patent,
        str(req.project_id),
        req.patent_number
    )
    
    return {"status": "queued"}

@router.get("/project/{project_id}/ingestion-status")
async def get_ingestion_status(
    project_id: UUID,
    current_user: User = Depends(get_current_user)
):
    from app.services.redis_service import get_subject_ingestion_status
    status_str = await get_subject_ingestion_status(str(project_id))
    if not status_str:
        return {"status": "none"}
    return json.loads(status_str)

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
