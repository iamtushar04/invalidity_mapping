import asyncio
import random
import logging
from app.services.patent_fetch import patent_fetch_service
from app.embedding.qdrant_service import embed_patent
from app.services.redis_service import set_embed_status
from app.services.get_structured_abstract import get_abstract
from app.services.get_structured_claims import convert_claims
from app.services.get_structured_description import process_structured_description
from app.embedding.text_utils import normalize_patent_number
from app.tasks.background_jobs import bg_session_maker

logger = logging.getLogger(__name__)

# Semaphores to limit concurrency
# We can fetch 5 patents concurrently from APIs
FETCH_SEMAPHORE = asyncio.Semaphore(5)
# We can embed up to 3 patents concurrently utilizing the ProcessPoolExecutor
EMBED_SEMAPHORE = asyncio.Semaphore(3)

from app.core.logger import current_user_id, current_project_id
from sqlalchemy import update
from app.database import SessionLocal
from app.models.patent import Patent
from app.services.priort_art_extractor import fetch_patent_data
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def _pipeline_fetch_and_embed(project_id: str, user_id: str, patent_number: str):
    """
    Pipelines the fetching and embedding of a single patent.
    Updates Redis status at each step, and Postgres when fetched.
    Automatically retries on failure.
    """
    # 0. Set context for the dynamic logger!
    current_user_id.set(user_id)
    current_project_id.set(project_id)
    
    logger.info(f"Starting pipeline for patent {patent_number}")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 1. Fetching Phase
            logger.info("Step 1: Setting status to fetching")
            await set_embed_status(project_id, patent_number, "fetching")
            
            async with FETCH_SEMAPHORE:
                # 1a. Fetch raw JSON (needed for embeddings: structured_description, etc.)
                raw_data = await fetch_patent_data(patent_number)
                if "error" in raw_data or "error_message" in raw_data:
                    raise ValueError(f"Failed to fetch raw data for {patent_number}: {raw_data}")

                # 1b. Fetch LLM enriched data (needed for Postgres DB)
                enriched_data = await patent_fetch_service.fetch_patent(patent_number)
            logger.info("Successfully fetched raw data for patent %s", patent_number)
            # Parse data out of the raw fetch results for Qdrant
            s_abstract = get_abstract(raw_data)
            s_claims = convert_claims(raw_data)
            s_desc = process_structured_description(
                structured_description=raw_data.get("structured_description", []),
                patent_number=raw_data.get("patent_number", patent_number),
                title=raw_data.get("title", ""),
                classifications=raw_data.get("classifications", [])
            )
            canonical_patent = normalize_patent_number(raw_data.get("patent_number") or patent_number)

            # Save enriched metadata to Postgres (title, abstract, etc.)
            # NOTE: fetch_status stays as "fetching" here — we ONLY set it to "success"
            # AFTER Qdrant embedding succeeds below. This prevents the desync bug where
            # Postgres says "success" but Qdrant has no data due to a connection failure.
            async with SessionLocal() as db:
                await db.execute(
                    update(Patent)
                    .where(Patent.project_id == project_id, Patent.patent_number == patent_number)
                    .values(
                        title=enriched_data.get("title", ""),
                        abstract=enriched_data.get("abstract", ""),
                        assignee=enriched_data.get("assignee", ""),
                        fetch_status="fetching",  # Still in progress — Qdrant not done yet
                        structured_summary=enriched_data.get("structured_summary", {}),
                    )
                )
                await db.commit()

            # 2. Embedding Phase — Qdrant MUST succeed before we mark "success"
            logger.info("Step 2: Saving to Qdrant embedding database...")
            await set_embed_status(project_id, patent_number, "embedding")
            force_reembed = True

            async with EMBED_SEMAPHORE:
                await embed_patent(
                    patent_number=canonical_patent,
                    abstract_data=s_abstract,
                    claims_data=s_claims,
                    description_data=s_desc,
                    project_id=project_id,
                    user_id=user_id,
                    force_reembed=force_reembed
                )

            # 3. Qdrant succeeded — NOW we can safely mark Postgres as "success"
            logger.info("Step 3: Pipeline completed successfully.")
            async with SessionLocal() as db:
                await db.execute(
                    update(Patent)
                    .where(Patent.project_id == project_id, Patent.patent_number == patent_number)
                    .values(fetch_status="success")
                )
                await db.commit()
            await set_embed_status(project_id, patent_number, "done")
            return  # Exit the loop on success
            
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed for patent {patent_number}: {e}")
            
            # --- FAST FAILURE (Non-Retryable Errors) ---
            fatal_keywords = [
                "404", "unauthorized", "401", "403", "forbidden", 
                "authentication", "insufficient_quota", "collection not found"
            ]
            is_fatal = any(keyword in error_msg for keyword in fatal_keywords)
            
            if is_fatal or attempt >= max_retries - 1:
                if is_fatal:
                    logger.error(f"Fatal error detected for {patent_number}. Skipping retries. Error: {e}")
                
                # Final failure (either fatal or out of retries)
                await set_embed_status(project_id, patent_number, "failed")
                try:
                    async with SessionLocal() as db:
                        await db.execute(
                            update(Patent)
                            .where(Patent.project_id == project_id, Patent.patent_number == patent_number)
                            .values(fetch_status="failed")
                        )
                        await db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to update db status for {patent_number}: {db_err}")
                
                return  # Exit the loop entirely on fatal error or max retries
            # -------------------------------------------

            # If it's a temporary error and we have retries left, wait and retry
            # Exponential backoff: 30s on attempt 1, 60s on attempt 2.
            # Jitter: adds a random 0-15s offset so 200 patents don't all
            # wake up at the same millisecond and hammer the external API.
            await set_embed_status(project_id, patent_number, "pending")
            sleep_time = (30 * (attempt + 1)) + random.uniform(0, 15)
            logger.info(f"Retrying patent {patent_number} in {sleep_time:.1f}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(sleep_time)

# --- DEPRECATED CHUNK-BASED BATCH EMBED (KEPT FOR REFERENCE) ---
async def _old_background_batch_embed(project_id: str, user_id: str, patent_numbers: list[str]):
    """
    Background task to run the pipeline for multiple patents concurrently in chunks of 5.
    Creates AnalysisJob tracking records and triggers matrix processing dynamically per chunk.
    """
    span = trace.get_current_span()
    span.set_attribute("project_id", project_id)
    span.set_attribute("patent_count", len(patent_numbers))
    
    if not patent_numbers:
        return

    # Set all to pending immediately
    for p in patent_numbers:
        await set_embed_status(project_id, p, "pending")
    
    chunk_size = 5
    for i in range(0, len(patent_numbers), chunk_size):
        chunk = patent_numbers[i:i + chunk_size]
        
        # Fire off pipelines for this chunk concurrently
        tasks = [
            _pipeline_fetch_and_embed(project_id, user_id, p)
            for p in chunk
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # SAFETY NET: Check if any tasks crashed catastrophically
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                stuck_patent = chunk[idx]
                logger.error(f"CRITICAL PIPELINE ERROR: Unhandled exception escaped for patent {stuck_patent}. Exception: {result}")
                
                try:
                    await set_embed_status(project_id, stuck_patent, "failed")
                    async with SessionLocal() as db:
                        await db.execute(
                            update(Patent)
                            .where(Patent.project_id == project_id, Patent.patent_number == stuck_patent)
                            .values(fetch_status="failed")
                        )
                        await db.commit()
                except Exception as e:
                    logger.error(f"Failed to force failure status for stuck patent {stuck_patent}: {e}")

        # --- AUTO-TRIGGER OBVIOUSNESS ANALYSIS FOR THIS CHUNK ---
        try:
            from app.models.project import Project
            from sqlalchemy import select
            import uuid
            from app.tasks.background_jobs import run_obviousness_mapping_task
            from app.models.analysis_job import AnalysisJob

            async with SessionLocal() as db:
                res_proj = await db.execute(
                    select(Project).where(Project.id == uuid.UUID(project_id))
                )
                project = res_proj.scalars().first()
                if project and project.selected_claim_ids:
                    # Find Patent IDs for this chunk that successfully embedded
                    res_pats = await db.execute(
                        select(Patent).where(
                            Patent.project_id == project_id,
                            Patent.patent_number.in_(chunk),
                            Patent.fetch_status == "success"
                        )
                    )
                    chunk_patents = res_pats.scalars().all()
                    
                    if chunk_patents:
                        # Queue AnalysisJob tracker records for progress bar visibility
                        for pat in chunk_patents:
                            res_job = await db.execute(
                                select(AnalysisJob).where(
                                    AnalysisJob.project_id == project_id,
                                    AnalysisJob.reference_patent_id == pat.id
                                )
                            )
                            if not res_job.scalars().first():
                                db.add(AnalysisJob(
                                    project_id=project_id,
                                    reference_patent_id=pat.id,
                                    status="pending"
                                ))
                        await db.commit()
                        
                        logger.info(f"Auto-triggering obviousness analysis for {len(chunk_patents)} chunk patents across {len(project.selected_claim_ids)} claims.")
                        chunk_patent_ids = [pat.id for pat in chunk_patents]
                        for claim_id in project.selected_claim_ids:
                            asyncio.create_task(run_obviousness_mapping_task(project.id, claim_id, chunk_patent_ids))
        except Exception as e:
            logger.error(f"Failed to auto-trigger obviousness analysis: {e}")

        # --- HEARTBEAT FOR REMAINING PATENTS ---
        # Refresh the Redis TTL for all remaining patents in the queue to prevent false-positive Sweeper failures
        remaining_patents = patent_numbers[i + chunk_size:]
        if remaining_patents:
            refresh_tasks = [
                set_embed_status(project_id, p, "pending")
                for p in remaining_patents
            ]
            await asyncio.gather(*refresh_tasks)

@tracer.start_as_current_span("background_batch_embed")
async def background_batch_embed(project_id: str, user_id: str, patent_numbers: list[str]):
    """
    Background task to run the pipeline for multiple patents using a Continuous Queue (Worker Pool).
    Creates AnalysisJob tracking records and triggers matrix processing dynamically per patent instantly.
    """
    span = trace.get_current_span()
    span.set_attribute("project_id", project_id)
    span.set_attribute("patent_count", len(patent_numbers))
    
    if not patent_numbers:
        return

    # 1. Create the Queue and load all patents into it
    queue = asyncio.Queue()
    for p in patent_numbers:
        # Set to pending initially
        await set_embed_status(project_id, p, "pending")
        queue.put_nowait(p)
        
    # 2. Define the continuous Worker
    async def worker():
        while True:
            # Grab the next patent in line
            current_patent = await queue.get()
            try:
                # Run the main pipeline (Fetch -> Embed -> Save)
                await _pipeline_fetch_and_embed(project_id, user_id, current_patent)
                
                # --- INSTANT OBVIOUSNESS TRIGGER ---
                # Check if it succeeded, and if so, trigger charting immediately
                from app.models.project import Project
                from sqlalchemy import select
                import uuid
                from app.tasks.background_jobs import run_obviousness_mapping_task
                from app.models.analysis_job import AnalysisJob
                
                async with SessionLocal() as db:
                    res_proj = await db.execute(select(Project).where(Project.id == uuid.UUID(project_id)))
                    project = res_proj.scalars().first()
                    
                    if project and project.selected_claim_ids:
                        res_pat = await db.execute(
                            select(Patent).where(
                                Patent.project_id == project_id,
                                Patent.patent_number == current_patent,
                                Patent.fetch_status == "success"
                            )
                        )
                        pat = res_pat.scalars().first()
                        
                        if pat:
                            # Queue AnalysisJob tracker record for the UI
                            res_job = await db.execute(
                                select(AnalysisJob).where(
                                    AnalysisJob.project_id == project_id,
                                    AnalysisJob.reference_patent_id == pat.id
                                )
                            )
                            if not res_job.scalars().first():
                                db.add(AnalysisJob(
                                    project_id=project_id,
                                    reference_patent_id=pat.id,
                                    status="pending"
                                ))
                            await db.commit()
                            
                            # Fire background obviousness task instantly for this 1 patent
                            for claim_id in project.selected_claim_ids:
                                asyncio.create_task(run_obviousness_mapping_task(project.id, claim_id, [pat.id]))
                                
            except Exception as e:
                logger.error(f"CRITICAL PIPELINE ERROR for patent {current_patent}: {e}")
                try:
                    await set_embed_status(project_id, current_patent, "failed")
                    async with SessionLocal() as db:
                        await db.execute(
                            update(Patent)
                            .where(Patent.project_id == project_id, Patent.patent_number == current_patent)
                            .values(fetch_status="failed")
                        )
                        await db.commit()
                except Exception as db_err:
                    logger.error(f"Failed to force failure status: {db_err}")
            finally:
                # Always tell the queue this task is complete
                queue.task_done()

    # 3. Define the Heartbeat Daemon
    async def heartbeat_daemon():
        while True:
            # Refresh Redis TTL to 20 minutes for anything still sitting in the queue
            remaining_patents = list(queue._queue)
            if remaining_patents:
                refresh_tasks = [set_embed_status(project_id, p, "pending") for p in remaining_patents]
                await asyncio.gather(*refresh_tasks)
            
            # Go to sleep for 5 minutes before checking and refreshing again
            await asyncio.sleep(300)

    # 4. Engine Start: Spawn workers and wait
    # Launch exactly 8 continuous workers (5 for fetching + 3 for embedding simultaneously)
    workers = [asyncio.create_task(worker()) for _ in range(8)]
    
    # Launch the 1 heartbeat daemon
    heartbeat_task = asyncio.create_task(heartbeat_daemon())
    
    # Wait right here until the entire queue is completely empty
    await queue.join()
    
    # Engine Stop: Clean up and kill the background tasks
    for w in workers:
        w.cancel()
    heartbeat_task.cancel()
    logger.info(f"Finished continuous queue batch processing for {len(patent_numbers)} patents.")
