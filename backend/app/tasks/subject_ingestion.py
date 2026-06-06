import logging
import asyncio
from uuid import UUID
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.tasks.background_jobs import bg_session_maker
from app.models.project import Project
from app.models.patent import Patent
from app.models.claim import Claim
from app.services.patent_fetch import patent_fetch_service
from app.services.redis_service import set_subject_ingestion_status
from app.core.logger import current_project_id

logger = logging.getLogger(__name__)

async def update_status(project_id: str, status: str, message: str, progress: int):
    payload = json.dumps({"status": status, "message": message, "progress": progress})
    await set_subject_ingestion_status(project_id, payload)
    logger.info(f"Subject Ingestion [{project_id}]: {message}")

async def background_ingest_subject_patent(project_id: str, patent_number: str):
    current_project_id.set(project_id)
    
    await update_status(project_id, "processing", f"Connecting to Google Patents to fetch {patent_number}...", 10)
    
    async with bg_session_maker() as db:
        try:
            res_proj = await db.execute(select(Project).where(Project.id == UUID(project_id)))
            project = res_proj.scalars().first()
            if not project:
                await update_status(project_id, "failed", "Project not found.", 0)
                return

            await update_status(project_id, "processing", "Downloading patent text and abstract...", 30)
            
            try:
                patent_data = await patent_fetch_service.fetch_patent(patent_number)
            except ValueError as e:
                await update_status(project_id, "failed", f"Failed to fetch patent: {e}", 0)
                return
                
            await update_status(project_id, "processing", "Extracting claims and descriptions...", 60)
            
            patent = Patent(
                project_id=UUID(project_id),
                patent_number=patent_data["patent_number"],
                title=patent_data["title"],
                abstract=patent_data["abstract"],
                assignee=patent_data["assignee"],
                is_reference=False,
                fetch_status="success",
                structured_summary=patent_data["structured_summary"]
            )
            
            db.add(patent)
            await db.flush()
            
            await update_status(project_id, "processing", f"Saving {len(patent_data['claims'])} claims to database...", 85)
            
            for c in patent_data["claims"]:
                claim = Claim(
                    patent_id=patent.id,
                    claim_number=c["claim_number"],
                    claim_text=c["claim_text"],
                    claim_type=c["claim_type"]
                )
                db.add(claim)
                
            project.subject_patent_id = patent.id
            await db.commit()
            
            await update_status(project_id, "success", "Subject patent successfully ingested!", 100)
            
        except Exception as e:
            logger.error(f"Unexpected error in background ingestion: {e}")
            await update_status(project_id, "failed", f"Unexpected error: {str(e)}", 0)
