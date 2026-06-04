from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from uuid import UUID
from datetime import datetime

from app.database import get_db
from app.models.project import Project
from app.models.patent import Patent
from app.models.claim import Claim
from app.models.mapping import ClaimElement, Mapping
from app.models.claim_chart import ClaimChart
from app.schemas.export import ClaimChartResponse, SaveChartEditsRequest
from app.services.export_service import export_service
from app.api.dependencies import get_current_user
from app.models.user import User

router = APIRouter()

@router.post("/{project_id}/charts/{reference_patent_id}/generate", response_model=ClaimChartResponse)
async def generate_or_fetch_claim_chart(
    project_id: UUID,
    reference_patent_id: UUID,
    force: bool = Query(False, description="Rebuild chart from latest mappings"),
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
        
    # Check existing chart
    res_ch = await db.execute(
        select(ClaimChart).where(
            ClaimChart.project_id == project_id,
            ClaimChart.reference_patent_id == reference_patent_id
        )
    )
    chart = res_ch.scalars().first()
    if chart and not force:
        return chart
    if chart and force:
        await db.delete(chart)
        await db.flush()
        
    # Query mappings scoped to this project and reference patent
    res_maps = await db.execute(
        select(Mapping).where(
            Mapping.project_id == project_id,
            Mapping.reference_patent_id == reference_patent_id,
        )
    )
    mappings = res_maps.scalars().all()
    if not mappings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Obviousness mappings must be run before chart compilation."
        )
        
    # Get reference patent
    res_pat = await db.execute(select(Patent).where(Patent.id == reference_patent_id))
    ref_pat = res_pat.scalars().first()
    if not ref_pat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference patent not found.")
        
    # Compile rows
    chart_rows = []
    claim_id = None
    for m in mappings:
        claim_id = m.claim_id
        
        # Query element
        res_el = await db.execute(select(ClaimElement).where(ClaimElement.id == m.element_id))
        el = res_el.scalars().first()
        
        # Query claim details
        res_cl = await db.execute(select(Claim).where(Claim.id == m.claim_id))
        cl = res_cl.scalars().first()
        
        claim_text = el.text if el else (cl.claim_text if cl else "")
        if el and getattr(el, "comment", None):
            claim_text = f"{claim_text}\n\n[User Note: {el.comment}]"

        # ON-DEMAND LLM GENERATION: If rationale is missing (because we used fast similarity), trigger LLM now
        if not m.rationale or m.rationale.startswith("Rationale generation failed") or "Analysis deferred" in m.rationale or force:
            from app.services.mapping_engine import mapping_engine_service
            
            saved_snippets = None
            best_payload = None
            if isinstance(m.cited_passage, dict):
                saved_snippets = m.cited_passage.get("saved_snippets")
                best_payload = m.cited_passage.get("best_payload")

            comparison = await mapping_engine_service.compare_element_to_patent(
                claim_text,
                el.element_id if el else "",
                ref_pat.abstract or "",
                ref_pat.patent_number,
                str(project_id),
                str(current_user.id),
                saved_snippets=saved_snippets,
                best_payload=best_payload
            )
            import logging
            logging.info(f"COMPARISON GENERATED: {comparison}")
            
            m.classification = comparison["classification"]
            m.cited_passage = comparison["cited_passage"]
            m.rationale = comparison["rationale"]
            m.para_ref = comparison["para_ref"]
            m.fig_ref = comparison["fig_ref"]
            db.add(m)

        # Clean up any bleeding placeholders
        if m.analyst_override and "Analysis deferred" in m.analyst_override:
            m.analyst_override = None

        display_cited_passage = m.cited_passage
        if isinstance(display_cited_passage, dict):
            display_cited_passage = display_cited_passage.get("display_text", "")

        chart_rows.append({
            "element_id": el.element_id if el else "1A",
            "claim_text": claim_text,
            "cited_passage": m.analyst_override or display_cited_passage or "",
            "para_ref": m.para_ref or "",
            "fig_ref": m.fig_ref or "",
            "rationale": m.rationale or ""
        })
        
    # Sort chronologically
    chart_rows.sort(key=lambda c: c["element_id"])
    
    # Store chart record
    chart = ClaimChart(
        project_id=project_id,
        reference_patent_id=reference_patent_id,
        claim_id=claim_id,
        chart_rows=chart_rows
    )
    db.add(chart)
    await db.commit()
    await db.refresh(chart)
    return chart

@router.put("/{project_id}/charts/{reference_patent_id}", response_model=ClaimChartResponse)
async def save_claim_chart_edits(
    project_id: UUID,
    reference_patent_id: UUID,
    req: SaveChartEditsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    res_ch = await db.execute(
        select(ClaimChart).where(
            ClaimChart.project_id == project_id,
            ClaimChart.reference_patent_id == reference_patent_id
        )
    )
    chart = res_ch.scalars().first()
    if not chart:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim chart not found.")
        
    # Update chart rows
    # Convert Pydantic schemas to dict before saving inside DB
    rows_dict = [r.dict() for r in req.chart_rows]
    chart.chart_rows = rows_dict
    db.add(chart)
    
    # Dual-Table Synchronization: update source mappings table columns
    for row in rows_dict:
        # Resolve element
        res_el = await db.execute(
            select(ClaimElement).where(
                ClaimElement.claim_id == chart.claim_id,
                ClaimElement.element_id == row["element_id"]
            )
        )
        el = res_el.scalars().first()
        if el:
            await db.execute(
                update(Mapping)
                .where(
                    Mapping.claim_id == chart.claim_id,
                    Mapping.element_id == el.id,
                    Mapping.reference_patent_id == reference_patent_id
                )
                .values(
                    analyst_override=row["cited_passage"],
                    para_ref=row["para_ref"],
                    fig_ref=row["fig_ref"],
                    rationale=row["rationale"]
                )
            )
            
    await db.commit()
    await db.refresh(chart)
    return chart

@router.get("/{project_id}/charts/{reference_patent_id}/export")
async def download_claim_chart(
    project_id: UUID,
    reference_patent_id: UUID,
    format: str = Query(..., regex="^(docx|xlsx|pdf)$"),
    token: str = Query(...), # Enable token queries for direct link tags
    db: AsyncSession = Depends(get_db)
):
    # Verify token
    from app.core.security import decode_access_token
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token session.")
        
    res_ch = await db.execute(
        select(ClaimChart).where(
            ClaimChart.project_id == project_id,
            ClaimChart.reference_patent_id == reference_patent_id
        )
    )
    chart = res_ch.scalars().first()
    if not chart:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim chart not generated.")
        
    # Query patent numbers
    res_pat1 = await db.execute(select(Patent).where(Patent.id == chart.reference_patent_id))
    ref_pat = res_pat1.scalars().first()
    
    res_proj = await db.execute(select(Project).where(Project.id == project_id))
    proj = res_proj.scalars().first()
    subject_pat_num = "Subject"
    if proj and proj.subject_patent_id:
        res_pat2 = await db.execute(select(Patent).where(Patent.id == proj.subject_patent_id))
        sub_pat = res_pat2.scalars().first()
        if sub_pat:
            subject_pat_num = sub_pat.patent_number
            
    ref_pat_num = ref_pat.patent_number if ref_pat else "Reference"
    
    # Update exported parameters
    chart.exported_at = datetime.now()
    chart.export_format = format
    db.add(chart)
    await db.commit()
    
    # Compile document stream
    if format == "docx":
        stream = export_service.export_docx(subject_pat_num, ref_pat_num, chart.chart_rows)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"Claim_Chart_{subject_pat_num}_vs_{ref_pat_num}.docx"
    elif format == "xlsx":
        stream = export_service.export_xlsx(subject_pat_num, ref_pat_num, chart.chart_rows)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"Claim_Chart_{subject_pat_num}_vs_{ref_pat_num}.xlsx"
    else:
        stream = export_service.export_pdf(subject_pat_num, ref_pat_num, chart.chart_rows)
        media = "application/pdf"
        filename = f"Claim_Chart_{subject_pat_num}_vs_{ref_pat_num}.pdf"
        
    return StreamingResponse(
        stream,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
