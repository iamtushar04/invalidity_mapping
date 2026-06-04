from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any
from uuid import UUID

from app.database import get_db
from app.models.project import Project
from app.models.patent import Patent
from app.models.claim import Claim
from app.models.mapping import Mapping
from app.models.score import Score
from app.models.analysis_job import AnalysisJob
from app.schemas.analysis import AnalysisStatusResponse
from app.schemas.mapping import MatrixResponse
from app.tasks.background_jobs import run_obviousness_mapping_task
from app.api.dependencies import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/{project_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_obviousness_analysis(
    project_id: UUID,
    claim_id: UUID,
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

    # Clear old job logs
    res_job = await db.execute(select(AnalysisJob).where(AnalysisJob.project_id == project_id))
    for job in res_job.scalars().all():
        await db.delete(job)
        
    # Clear old cached claim charts so exports use fresh mappings
    from app.models.claim_chart import ClaimChart
    res_chart = await db.execute(select(ClaimChart).where(ClaimChart.project_id == project_id))
    for chart in res_chart.scalars().all():
        await db.delete(chart)
        
    await db.commit()

    # Delegate job processing asynchronously to BackgroundTasks
    background_tasks.add_task(run_obviousness_mapping_task, project_id, claim_id)
    return {"status": "started"}

@router.get("/{project_id}/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(
    project_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res_jobs = await db.execute(
        select(AnalysisJob).where(AnalysisJob.project_id == project_id)
    )
    jobs = res_jobs.scalars().all()
    if not jobs:
        return {"percent_complete": 0, "jobs": []}

    completed_jobs = sum(1 for j in jobs if j.status in ["completed", "failed"])
    percent = int((completed_jobs / len(jobs)) * 100)

    # Query patent numbers for response formatting
    job_details = []
    for j in jobs:
        res_pat = await db.execute(select(Patent).where(Patent.id == j.reference_patent_id))
        pat = res_pat.scalars().first()
        job_details.append({
            "reference_patent_id": j.reference_patent_id,
            "patent_number": pat.patent_number if pat else "Unknown",
            "status": j.status,
            "error_message": j.error_message
        })
    return {"percent_complete": percent, "jobs": job_details}

# New endpoint to split selected claims via LLM and assign weights
@router.post("/{project_id}/split", status_code=status.HTTP_200_OK)
async def split_claims(
    project_id: UUID,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Expect payload {'claim_ids': [list of claim UUID strings]}
    Calls LLM service to split claims into elements with weights.
    Returns mapping claim_id -> list of element dicts.
    """
    claim_ids = payload.get("claim_ids", [])
    if not claim_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="claim_ids list required")
    # Verify project ownership
    res_proj = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == current_user.id))
    project = res_proj.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    # Call the service function
    from app.services.claim_processor import split_claims_via_llm
    results = await split_claims_via_llm(str(project_id), claim_ids)
    return {"results": results}

@router.get("/{project_id}/matrix", response_model=MatrixResponse)
async def get_obviousness_matrix(
    project_id: UUID,
    claim_id: UUID = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Fetch all reference patents
    res_pat = await db.execute(
        select(Patent).where(Patent.project_id == project_id, Patent.is_reference == True)
    )
    references = res_pat.scalars().all()

    rows = []
    for ref in references:
        # Fetch score
        res_sc = await db.execute(select(Score).where(Score.reference_patent_id == ref.id))
        score_obj = res_sc.scalars().first()
        score = float(score_obj.score) if score_obj else 0.0

        # Fetch mappings
        query_maps = select(Mapping).where(Mapping.reference_patent_id == ref.id)
        if claim_id:
            query_maps = query_maps.where(Mapping.claim_id == claim_id)
        res_maps = await db.execute(query_maps)
        mappings = res_maps.scalars().all()

        # Format elements mapping cell list
        cells = []
        # Batch‑fetch ClaimElement objects for this reference patent
        element_ids = [m.element_id for m in mappings]
        elements_map: dict[int, Any] = {}
        if element_ids:
            from app.models.mapping import ClaimElement
            res_elements = await db.execute(
                select(ClaimElement).where(ClaimElement.id.in_(element_ids))
            )
            elements_map = {e.id: e for e in res_elements.scalars().all()}

        for m in mappings:
            # Retrieve the cached ClaimElement (or None if missing)
            el = elements_map.get(m.element_id)
            print(f"Fetch claim element {m.element_id} => {el}")
            if el:
                display_cited_passage = m.cited_passage
                if isinstance(display_cited_passage, dict):
                    display_cited_passage = display_cited_passage.get("display_text", "")
                elif not isinstance(display_cited_passage, str):
                    display_cited_passage = ""

                cells.append({
                    "element_id": el.element_id,
                    "element_text": el.text,
                    "cited_passage": display_cited_passage,
                    "classification": m.classification,
                    "analyst_classification": m.analyst_classification,
                })

        print("cells", cells)
        # Sort cells chronologically
        cells.sort(key=lambda c: c["element_id"])
        print("sorted cells", cells)
        rows.append({
            "reference_patent_id": ref.id,
            "patent_number": ref.patent_number,
            "title": ref.title,
            "score": score,
            "mappings": cells
        })
    return {"rows": rows}
