import traceback
import json
import logging

logger = logging.getLogger(__name__)
from app.services.get_structured_abstract import get_abstract
from app.services.get_structured_description import process_structured_description
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any
from uuid import UUID
import re
import io

from app.database import get_db
from app.models.patent import Patent
from app.models.project import Project
from app.schemas.patent import PatentResponse
from app.utils.excel_parser import excel_parser
from app.api.dependencies import get_current_user
from app.models.user import User
from app.services.priort_art_extractor import fetch_patent_data
from app.services.get_structured_claims import convert_claims
from app.tasks.embed_pipeline import background_batch_embed
from app.services.redis_service import get_all_embed_statuses, get_embed_status, set_embed_status
router = APIRouter()

from pydantic import BaseModel

class ManualArtNumbers(BaseModel):
    patent_numbers: str

@router.post("/{project_id}/numbers", status_code=status.HTTP_202_ACCEPTED)
async def queue_prior_art_numbers(
    project_id: UUID,
    req: ManualArtNumbers,
    background_tasks: BackgroundTasks,
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
        
    # Split manual list by any combination of commas, spaces, tabs, or newlines
    numbers = [n.strip() for n in re.split(r'[,\s]+', req.patent_numbers) if n.strip()]
    print("numbers => ",numbers)
      
    added_numbers = []
    duplicate_numbers = []
    # Store reference patent placeholders in DB
    for num in numbers:
        # Check if already added
        res_pat = await db.execute(
            select(Patent).where(Patent.project_id == project_id, Patent.patent_number == num)
        )
        existing_patent = res_pat.scalars().first()
        if existing_patent:
            if existing_patent.fetch_status == "failed":
                # Automatically retry failed patents instead of calling them duplicates
                existing_patent.fetch_status = "pending"
                await set_embed_status(str(project_id), num, "pending")
                added_numbers.append(num)
                continue
            elif existing_patent.fetch_status == "success":
                # Fix #3: Check for desync — Postgres says "success" but Redis shows
                # an active stale status, meaning Qdrant embedding never completed.
                redis_status = await get_embed_status(str(project_id), num)
                if redis_status in ("fetching", "pending", "embedding"):
                    # Desync detected — treat as failed and re-queue
                    logger.warning(f"Desync detected for patent {num}: Postgres=success but Redis={redis_status}. Re-queuing.")
                    existing_patent.fetch_status = "pending"
                    await set_embed_status(str(project_id), num, "pending")
                    added_numbers.append(num)
                    continue
                else:
                    # Genuinely successful — treat as duplicate
                    duplicate_numbers.append(num)
                    continue
            else:
                duplicate_numbers.append(num)
                continue
        
        patent = Patent(
            project_id=project_id,
            patent_number=num,
            is_reference=True,
            fetch_status="pending"
        )
        db.add(patent)
        added_numbers.append(num)
        
    await db.commit()

    # Trigger parallel fetch & embed pipeline in the background
    if added_numbers:
        background_tasks.add_task(
            background_batch_embed, 
            str(project_id), 
            str(current_user.id), 
            added_numbers
        )
    elif duplicate_numbers:
        if len(numbers) == 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Patent {numbers[0]} is already present in this project.")
        else:
            return {"status": "duplicate", "message": "All provided patents are already present.", "duplicates_skipped": len(duplicate_numbers)}

    return {"status": "queued", "count": len(added_numbers), "duplicates_skipped": len(duplicate_numbers)}

@router.get("/{project_id}/embed-status", status_code=status.HTTP_200_OK)
async def get_project_embed_statuses(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the embedding status for all prior art patents in a project.
    Reads directly from Redis.
    """
    # Fetch all prior art patents for this project
    res = await db.execute(
        select(Patent.patent_number)
        .where(Patent.project_id == project_id, Patent.is_reference == True)
    )
    patents = res.scalars().all()
    
    if not patents:
        return {"statuses": {}}

    statuses = await get_all_embed_statuses(str(project_id), patents)
    return {"statuses": statuses}

@router.post("/{project_id}/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_prior_art_excel(
    project_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
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
        
    content = await file.read()
    numbers = excel_parser.parse_patent_numbers(io.BytesIO(content))
    if not numbers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse patent numbers from Column A."
        )
        
    added_numbers = []
    duplicate_numbers = []
    for num in numbers:
        # Check if already added
        res_pat = await db.execute(
            select(Patent).where(Patent.project_id == project_id, Patent.patent_number == num)
        )
        existing_patent = res_pat.scalars().first()
        if existing_patent:
            if existing_patent.fetch_status == "failed":
                # Automatically retry failed patents in excel upload as well
                existing_patent.fetch_status = "pending"
                await set_embed_status(str(project_id), num, "pending")
                added_numbers.append(num)
                continue
            else:
                duplicate_numbers.append(num)
                continue
            
        patent = Patent(
            project_id=project_id,
            patent_number=num,
            is_reference=True,
            fetch_status="pending"
        )
        db.add(patent)
        added_numbers.append(num)
        
    await db.commit()
    
    # Trigger parallel fetch & embed pipeline in the background
    if added_numbers:
        background_tasks.add_task(
            background_batch_embed, 
            str(project_id), 
            str(current_user.id), 
            added_numbers
        )
    elif duplicate_numbers:
        if len(numbers) == 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Patent {numbers[0]} is already present in this project.")
        else:
            return {"status": "duplicate", "message": "All provided patents are already present.", "duplicates_skipped": len(duplicate_numbers)}

    return {"status": "queued", "count": len(added_numbers), "duplicates_skipped": len(duplicate_numbers)}

@router.post("/{project_id}/patent/{patent_number}/embed", status_code=status.HTTP_200_OK)
async def embed_single_patent(
    project_id: UUID,
    patent_number: str,
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

    # Find the patent in database
    res_pat = await db.execute(
        select(Patent).where(Patent.project_id == project_id, Patent.patent_number == patent_number)
    )
    patent = res_pat.scalars().first()
    if not patent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patent not found in project.")

    try:
        from app.embedding.qdrant_service import embed_patent
        from app.embedding.text_utils import normalize_patent_number
        # Fetch patent details
        patent_data = await fetch_patent_data(patent_number)
        if "error_message" in patent_data:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=patent_data["error_message"])

        structured_claims = convert_claims(patent_data)
        structured_description = process_structured_description(
            structured_description=patent_data["structured_description"],
            patent_number=patent_data["patent_number"],
            title=patent_data["title"],
            classifications=patent_data["classifications"]
        )
        structured_abstract = get_abstract(patent_data)

        # with open(f"structured_claims_{patent_number}.json", "w", encoding="utf-8") as f:
        #     json.dump(structured_claims, f, indent=2, ensure_ascii=False)
        
        # with open(f"structured_description_{patent_number}.json", "w", encoding="utf-8") as f:
        #     json.dump(structured_description, f, indent=2, ensure_ascii=False)
        
        # with open(f"structured_abstract_{patent_number}.json", "w", encoding="utf-8") as f:
        #     json.dump(structured_abstract, f, indent=2, ensure_ascii=False)
        

        # Call the embedding service
        logger.info(f"Step 3: Calling embedding service for {patent_number}")
        await set_embed_status(str(project_id), patent_number, "embedding")
        canonical_patent = normalize_patent_number(
            patent_data.get("patent_number") or patent_number
        )
        
        force_reembed = False
        if patent.fetch_status != "success":
            force_reembed = True
            
        is_skipped = await embed_patent(
            patent_number=canonical_patent,
            abstract_data=structured_abstract,
            claims_data=structured_claims,
            description_data=structured_description,
            project_id=str(project_id),
            user_id=str(current_user.id),
            force_reembed=force_reembed
        )
        
        if is_skipped:
            await set_embed_status(str(project_id), patent_number, "done")
            return {"status": "already_present", "message": f"Patent {patent_number} is already fully embedded."}

        # Update patent info in database
        patent.title = patent_data.get("title")
        patent.abstract = patent_data.get("abstract")
        assignees = patent_data.get("assignees", [])
        patent.assignee = assignees[0] if assignees else None
        patent.fetch_status = "success"
        
        # Populate structured summary format
        patent.structured_summary = {
            "core_inventive_concept": structured_abstract.get("metadata", {}).get("title", ""),
            "problem_solution_mapping": {
                "problem": structured_abstract.get("abstract", "")[:200],
                "solution": structured_abstract.get("abstract", "")[200:400]
            },
            "novelty_points": [c["code"] for c in structured_abstract.get("metadata", {}).get("classifications", [])]
        }
        
        db.add(patent)
        await db.commit()

        await set_embed_status(str(project_id), patent_number, "done")
        return {"status": "success", "message": f"Patent {patent_number} successfully embedded."}
    except Exception as e:
        patent.fetch_status = "failed"
        db.add(patent)
        await db.commit()
        await set_embed_status(str(project_id), patent_number, "failed")
        logger.error(f"========== EMBED ERROR ==========\nFailed to manually embed {patent_number}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{project_id}", response_model=List[PatentResponse])
async def list_reference_patents(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res_pat = await db.execute(
        select(Patent).where(Patent.project_id == project_id, Patent.is_reference == True)
    )
    return res_pat.scalars().all()
