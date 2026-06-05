from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import OperationalError, DBAPIError
from app.utils.db_retry import commit_with_retry
import logging
import asyncio
from uuid import UUID
from decimal import Decimal

from app.core.config import settings
from app.models.patent import Patent
from app.models.project import Project
from app.models.claim import Claim
from app.models.mapping import ClaimElement, Mapping
from app.models.score import Score
from app.models.analysis_job import AnalysisJob
from app.services.patent_fetch import patent_fetch_service
from app.services.mapping_engine import mapping_engine_service
from app.embedding.text_utils import normalize_patent_number

logger = logging.getLogger(__name__)

# Dedicated engine for background threads to avoid session collision
bg_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,      # Tests connection before using it — prevents stale connection errors
    pool_recycle=300,        # Refresh idle connections every 5 minutes
)
bg_session_maker = async_sessionmaker(bind=bg_engine, class_=AsyncSession, expire_on_commit=False)
from app.core.logger import current_project_id, current_user_id

async def run_obviousness_mapping_task(project_id: UUID, claim_id: UUID):
    async with bg_session_maker() as db:
        try:
            res_proj = await db.execute(select(Project).where(Project.id == project_id))
            project = res_proj.scalars().first()
            if not project:
                logger.warning("Project %s not found. Terminating obviousness task.", project_id)
                return
            user_id = str(project.user_id)
            
            # Set context for the dynamic logger so it writes to the correct files!
            current_project_id.set(str(project_id))
            current_user_id.set(user_id)
            
            logger.info("Starting background obviousness mapping task...")

            # 1. Fetch reference patents
            # Only fetch patents that have successfully completed the embedding pipeline!
            # Ignoring 'failed', 'pending', and 'fetching' patents prevents 409 Conflict crashes.
            res_pat = await db.execute(
                select(Patent).where(
                    Patent.project_id == project_id, 
                    Patent.is_reference == True,
                    Patent.fetch_status == "success"
                )
            )
            references = res_pat.scalars().all()
            
            # 2. Fetch claim elements
            res_el = await db.execute(select(ClaimElement).where(ClaimElement.claim_id == claim_id))
            elements = res_el.scalars().all()
            
            if not references or not elements:
                logger.warning("No references or elements found. Terminating obviousness task.")
                return
                
            # Initialize job status list to track
            for ref in references:
                res_job = await db.execute(
                    select(AnalysisJob).where(
                        AnalysisJob.project_id == project_id,
                        AnalysisJob.reference_patent_id == ref.id
                    )
                )
                if not res_job.scalars().first():
                    job = AnalysisJob(project_id=project_id, reference_patent_id=ref.id, status="pending")
                    db.add(job)
            await commit_with_retry(db)
            
            # Process sequentially
            for ref in references:
                ref_id = ref.id
                patent_number = ref.patent_number
                patent_abstract = ref.abstract or ""
                fetch_status = ref.fetch_status

                # Update status to running
                await db.execute(
                    update(AnalysisJob)
                    .where(AnalysisJob.project_id == project_id, AnalysisJob.reference_patent_id == ref_id)
                    .values(status="running")
                )
                await commit_with_retry(db)
                
                try:
                    # Fetch patent metadata if still pending
                    if fetch_status == "pending":
                        data = await patent_fetch_service.fetch_patent(patent_number)
                        await db.execute(
                            update(Patent)
                            .where(Patent.id == ref_id)
                            .values(
                                title=data["title"],
                                abstract=data["abstract"],
                                assignee=data["assignee"],
                                fetch_status="success",
                                structured_summary=data["structured_summary"],
                            )
                        )
                        await db.flush()
                        patent_abstract = data["abstract"] or ""
                        fetch_status = "success"

                        # ✅ FIX (P0): Embed the prior-art patent into Qdrant so that
                        # search_element_in_prior_art() can find relevant passages.
                        # Without this, every element comparison returns empty results.
                        try:
                            from app.embedding.qdrant_service import embed_patent as _embed_patent
                            from app.services.get_structured_abstract import get_abstract
                            from app.services.get_structured_claims import convert_claims
                            from app.services.get_structured_description import process_structured_description

                            s_claims = convert_claims(data)
                            s_desc = process_structured_description(
                                structured_description=data["structured_description"],
                                patent_number=data["patent_number"],
                                title=data["title"],
                                classifications=data["classifications"],
                            )
                            s_abstract = get_abstract(data)
                            canonical = normalize_patent_number(
                                data.get("patent_number") or patent_number
                            )
                            await _embed_patent(
                                patent_number=canonical,
                                abstract_data=s_abstract,
                                claims_data=s_claims,
                                description_data=s_desc,
                                project_id=str(project_id),
                                user_id=user_id,
                            )
                            logger.info(
                                "Embedded prior-art %s into Qdrant for project %s",
                                canonical, project_id
                            )
                        except Exception as embed_err:
                            logger.error(
                                "Failed to embed prior-art %s: %s",
                                patent_number, embed_err
                            )

                    else:
                        # Patent already fetched (fetch_status == "success").
                        # Guard: verify vectors actually exist in Qdrant for this
                        # project+user+patent. If not (e.g. the /embed step was
                        # skipped, or old data was embedded with broken payloads),
                        # re-fetch and re-embed now so the search will have results.
                        try:
                            from app.embedding.qdrant_service import (
                                embed_patent as _embed_patent,
                                _CLIENT,
                                _COLLECTION_NAME,
                            )
                            from app.services.get_structured_abstract import get_abstract
                            from app.services.get_structured_claims import convert_claims
                            from app.services.get_structured_description import process_structured_description
                            from qdrant_client.models import Filter, FieldCondition, MatchValue

                            canonical = normalize_patent_number(patent_number)
                            existing, _ = _CLIENT.scroll(
                                collection_name=_COLLECTION_NAME,
                                scroll_filter=Filter(
                                    must=[
                                        FieldCondition(
                                            key="project_id",
                                            match=MatchValue(value=str(project_id)),
                                        ),
                                        FieldCondition(
                                            key="user_id",
                                            match=MatchValue(value=user_id),
                                        ),
                                        FieldCondition(
                                            key="patent_number",
                                            match=MatchValue(value=canonical),
                                        ),
                                    ]
                                ),
                                limit=1,
                                with_vectors=False,
                            )

                            if not existing:
                                logger.warning(
                                    "Patent %s has fetch_status=success but no Qdrant vectors "
                                    "for project %s / user %s — re-fetching and re-embedding.",
                                    patent_number, project_id, user_id,
                                )
                                data = await patent_fetch_service.fetch_patent(patent_number)
                                s_claims = convert_claims(data)
                                s_desc = process_structured_description(
                                    structured_description=data["structured_description"],
                                    patent_number=data["patent_number"],
                                    title=data["title"],
                                    classifications=data["classifications"],
                                )
                                s_abstract = get_abstract(data)
                                canonical2 = normalize_patent_number(
                                    data.get("patent_number") or patent_number
                                )
                                await _embed_patent(
                                    patent_number=canonical2,
                                    abstract_data=s_abstract,
                                    claims_data=s_claims,
                                    description_data=s_desc,
                                    project_id=str(project_id),
                                    user_id=user_id,
                                )
                                logger.info(
                                    "Re-embedded prior-art %s into Qdrant for project %s",
                                    canonical2, project_id,
                                )
                            else:
                                logger.debug(
                                    "Patent %s already has Qdrant vectors for project %s — skipping re-embed.",
                                    patent_number, project_id,
                                )
                        except Exception as guard_err:
                            logger.error(
                                "Qdrant guard-check / re-embed failed for %s: %s",
                                patent_number, guard_err,
                            )
                        
                    # Cache Check: Do we already have all mappings for this patent and claim?
                    res_maps_check = await db.execute(
                        select(Mapping).where(
                            Mapping.claim_id == claim_id,
                            Mapping.reference_patent_id == ref_id
                        )
                    )
                    existing_mappings = res_maps_check.scalars().all()
                    
                    has_pending = any(m.classification == "Pending" for m in existing_mappings)
                    
                    if existing_mappings and len(existing_mappings) == len(elements) and not has_pending:
                        logger.info(f"Step 2: Found {len(existing_mappings)} existing mappings for reference patent {patent_number}. Skipping LLM.")
                        
                        weighted_score = 0.0
                        for el in elements:
                            mapping = next((m for m in existing_mappings if m.element_id == el.id), None)
                            if mapping:
                                impact = 0.0
                                cls = mapping.analyst_classification or mapping.classification
                                if cls == "Y": impact = 1.0
                                elif cls == "Obviousness": impact = 0.75
                                elif cls in ("Partial", "P"): impact = 0.50
                                weighted_score += float(el.weight) * impact
                                
                    else:
                        # Cleanup any weird duplicates or partial sets before asking OpenAI
                        if existing_mappings:
                            logger.info(f"Step 2: Cleaning up {len(existing_mappings)} incomplete mappings to prevent duplicates.")
                            await db.execute(
                                delete(Mapping).where(
                                    Mapping.claim_id == claim_id,
                                    Mapping.reference_patent_id == ref_id
                                )
                            )
                            await commit_with_retry(db)
                            
                        # Create fast similarity-based mappings for the Matrix UI
                        weighted_score = 0.0
                        for el in elements:
                            # Use fast Qdrant vector similarity to estimate Y/P/N instantly
                            search_text = f"{el.text}\nContext/Interpretation: {el.comment}" if getattr(el, "comment", None) else el.text
                            fast_comparison = await mapping_engine_service.fast_compare_element_to_patent(
                                search_text,
                                el.element_id,
                                patent_number,
                                str(project_id),
                                user_id,
                            )
                            
                            classification = fast_comparison["classification"]
                            cited_passage_data = {
                                "display_text": fast_comparison["cited_passage"],
                                "saved_snippets": fast_comparison.get("saved_snippets", []),
                                "best_payload": fast_comparison.get("best_payload", {})
                            }
                            rationale = fast_comparison["rationale"]
                            para_ref = fast_comparison["para_ref"]
                            fig_ref = fast_comparison["fig_ref"]
                            
                            # RACE CONDITION FAILSAFE: 
                            # Check if another background job inserted this exact mapping
                            res_map_final = await db.execute(
                                select(Mapping).where(
                                    Mapping.claim_id == claim_id,
                                    Mapping.element_id == el.id,
                                    Mapping.reference_patent_id == ref_id
                                )
                            )
                            existing_mapping = res_map_final.scalars().first()
                            
                            if existing_mapping:
                                # Only overwrite if it was completely blank/Pending, don't destroy actual LLM data
                                if existing_mapping.classification in (None, "Pending", "N"):
                                    existing_mapping.classification = classification
                                    existing_mapping.cited_passage = cited_passage_data
                                    existing_mapping.rationale = rationale
                                    existing_mapping.para_ref = para_ref
                                    existing_mapping.fig_ref = fig_ref
                                mapping = existing_mapping
                            else:
                                mapping = Mapping(
                                    project_id=project_id,
                                    claim_id=claim_id,
                                    element_id=el.id,
                                    reference_patent_id=ref_id,
                                    classification=classification,
                                    cited_passage=cited_passage_data,
                                    rationale=rationale,
                                    para_ref=para_ref,
                                    fig_ref=fig_ref
                                )
                                db.add(mapping)
                            await commit_with_retry(db)
                            logger.info("Deferred mapping saved for claim %s and element %s", claim_id, el.id)
                            
                            # Add score impact
                            impact = 0.0
                            if classification == "Y": impact = 1.0
                            elif classification in ("Partial", "P"): impact = 0.50
                            
                            logger.info(f"Score Calculation: Element {el.id} classified as '{classification}'. Impact factor: {impact}. Weight: {el.weight}.")
                            weighted_score += float(el.weight) * impact
                        
                    # Normalize the score to be out of 100%
                    total_weight = sum(float(el.weight) for el in elements)
                    final_score = (weighted_score / total_weight * 100.0) if total_weight > 0 else 0.0
                    
                    logger.info(f"Score Calculation Complete: Final obviousness score against patent {patent_number} is {final_score:.2f}% (Total weight considered: {total_weight})")
                    
                    # Save calculated obviousness score
                    res_sc = await db.execute(
                        select(Score).where(Score.claim_id == claim_id, Score.reference_patent_id == ref_id)
                    )
                    score = res_sc.scalars().first()
                    if not score:
                        score = Score(
                            project_id=project_id,
                            claim_id=claim_id,
                            reference_patent_id=ref_id,
                            score=Decimal(str(round(final_score, 2)))
                        )
                        db.add(score)
                    else:
                        score.score = Decimal(str(round(final_score, 2)))
                        db.add(score)
                        
                    # Mark job complete
                    await db.execute(
                        update(AnalysisJob)
                        .where(AnalysisJob.project_id == project_id, AnalysisJob.reference_patent_id == ref_id)
                        .values(status="completed")
                    )
                    await commit_with_retry(db)
                    
                except Exception as ex:
                    logger.error(f"Failed to process patent obviousness comparison: {ex}")
                    await db.rollback()
                    await db.execute(
                        update(AnalysisJob)
                        .where(AnalysisJob.project_id == project_id, AnalysisJob.reference_patent_id == ref_id)
                        .values(status="failed", error_message=str(ex))
                    )
                    await commit_with_retry(db)
                    
                # Small throttle to simulate real async execution
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Global obviousness analysis thread failure: {e}")
