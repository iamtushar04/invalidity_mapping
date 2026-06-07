import logging
import asyncio
from uuid import UUID
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import SessionLocal
from app.models.project import Project
from app.models.patent import Patent
from app.models.claim import Claim
from app.models.mapping import ClaimElement, Mapping
from app.models.claim_chart import ClaimChart
from app.utils.db_retry import commit_with_retry
from app.services.redis_service import set_chart_status
from app.services.mapping_engine import mapping_engine_service

logger = logging.getLogger(__name__)

def natural_keys(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("process_single_chart")
async def process_single_chart(db: AsyncSession, project_id: str, user_id: str, ref_id: str):
    span = trace.get_current_span()
    span.set_attribute("project_id", project_id)
    span.set_attribute("reference_patent_id", ref_id)
    try:
        project_uuid = UUID(project_id)
        ref_uuid = UUID(ref_id)
        
        # Check existing chart
        res_ch = await db.execute(
            select(ClaimChart).where(
                ClaimChart.project_id == project_uuid,
                ClaimChart.reference_patent_id == ref_uuid
            )
        )
        chart = res_ch.scalars().first()
        if chart:
            await db.delete(chart)
            await db.flush()
            
        res_maps = await db.execute(
            select(Mapping).where(
                Mapping.project_id == project_uuid,
                Mapping.reference_patent_id == ref_uuid,
            )
        )
        mappings = res_maps.scalars().all()
        if not mappings:
            logger.warning(f"No mappings found for chart generation {ref_id}")
            return
            
        res_pat = await db.execute(select(Patent).where(Patent.id == ref_uuid))
        ref_pat = res_pat.scalars().first()
        if not ref_pat:
            logger.warning(f"Ref patent not found {ref_id}")
            return
            
        chart_rows = []
        claim_id = None
        seen_elements = set()
        llm_score = 0.0
        total_weight = 0.0
        
        for m in mappings:
            claim_id = m.claim_id
            
            res_el = await db.execute(select(ClaimElement).where(ClaimElement.id == m.element_id))
            el = res_el.scalars().first()
            element_str_id = el.element_id if el else "1A"
            
            if element_str_id in seen_elements:
                continue
            seen_elements.add(element_str_id)
            
            res_cl = await db.execute(select(Claim).where(Claim.id == m.claim_id))
            cl = res_cl.scalars().first()
            
            claim_text = el.text if el else (cl.claim_text if cl else "")
            if el and getattr(el, "comment", None):
                claim_text = f"{claim_text}\n\n[User Note: {el.comment}]"

            if not m.rationale or m.rationale.startswith("Rationale generation failed") or "Analysis deferred" in m.rationale:
                saved_snippets = None
                best_payload = None
                if isinstance(m.cited_passage, dict):
                    saved_snippets = m.cited_passage.get("saved_snippets")
                    best_payload = m.cited_passage.get("best_payload")

                comparison = None
                for attempt in range(3):
                    try:
                        comparison = await mapping_engine_service.compare_element_to_patent(
                            claim_text,
                            el.element_id if el else "",
                            ref_pat.abstract or "",
                            ref_pat.patent_number,
                            project_id,
                            user_id,
                            saved_snippets=saved_snippets,
                            best_payload=best_payload
                        )
                        break
                    except Exception as llm_err:
                        logger.warning(f"LLM Chart generation failed (attempt {attempt+1}/3) for element {element_str_id}: {llm_err}")
                        if attempt == 2:
                            raise
                        await asyncio.sleep(5)
                
                llm_class = comparison["classification"]
                if isinstance(m.cited_passage, dict):
                    m.cited_passage = {
                        **m.cited_passage,
                        "display_text": comparison["cited_passage"]
                    }
                else:
                    m.cited_passage = {
                        "display_text": comparison["cited_passage"],
                        "saved_snippets": comparison.get("saved_snippets", []),
                        "best_payload": comparison.get("best_payload", {})
                    }
                
                m.rationale = comparison["rationale"]
                m.para_ref = comparison["para_ref"]
                m.fig_ref = comparison["fig_ref"]
                db.add(m)
            else:
                llm_class = m.classification

            if m.analyst_override and "Analysis deferred" in m.analyst_override:
                m.analyst_override = None

            display_cited_passage = m.cited_passage
            if isinstance(display_cited_passage, dict):
                display_cited_passage = display_cited_passage.get("display_text", "")

            # Use analyst override if present, else use LLM classification
            final_class = m.analyst_classification or llm_class
            
            # Calculate score impact
            weight = float(el.weight) if el and el.weight else 1.0
            impact = 0.0
            if final_class == "Y": impact = 1.0
            elif final_class == "Obviousness": impact = 0.75
            elif final_class in ("Partial", "P"): impact = 0.50
            llm_score += weight * impact
            total_weight += weight

            chart_rows.append({
                "element_id": element_str_id,
                "claim_text": claim_text,
                "cited_passage": m.analyst_override or display_cited_passage or "",
                "para_ref": m.para_ref or "",
                "fig_ref": m.fig_ref or "",
                "rationale": m.rationale or "",
                "classification": final_class
            })
            
        chart_rows.sort(key=lambda c: natural_keys(c["element_id"]))
        
        final_llm_score = (llm_score / total_weight * 100.0) if total_weight > 0 else 0.0
        
        new_chart = ClaimChart(
            project_id=project_uuid,
            reference_patent_id=ref_uuid,
            claim_id=claim_id,
            chart_rows=chart_rows,
            llm_score=final_llm_score
        )
        db.add(new_chart)
        await commit_with_retry(db)
        await set_chart_status(project_id, ref_id, "done")
        
    except Exception as e:
        logger.error(f"Failed to process chart for {ref_id}: {e}")
        await set_chart_status(project_id, ref_id, "failed")

@tracer.start_as_current_span("background_generate_multiple_charts")
async def background_generate_multiple_charts(project_id: str, user_id: str, ref_ids: list[str]):
    span = trace.get_current_span()
    span.set_attribute("project_id", project_id)
    span.set_attribute("chart_count", len(ref_ids))
    for ref_id in ref_ids:
        await set_chart_status(project_id, ref_id, "processing")
        
    sem = asyncio.Semaphore(3)
    
    async def _safe_process(r_id: str):
        async with sem:
            try:
                async with SessionLocal() as db:
                    await process_single_chart(db, project_id, user_id, r_id)
            except Exception as e:
                logger.error(f"Outer task exception for {r_id}: {e}")
                await set_chart_status(project_id, r_id, "failed")

    tasks = [_safe_process(r_id) for r_id in ref_ids]
    await asyncio.gather(*tasks)
