import asyncio
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
# We can embed 1 patent at a time on the CPU to avoid GIL thrashing and maximize speed
EMBED_SEMAPHORE = asyncio.Semaphore(1)

from app.core.logger import current_user_id, current_project_id
from sqlalchemy import update
from app.database import SessionLocal
from app.models.patent import Patent
from app.services.priort_art_extractor import fetch_patent_data

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
            print(raw_data, "RAW DATA")
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

            # Update Postgres DB with the LLM enriched data
            async with SessionLocal() as db:
                await db.execute(
                    update(Patent)
                    .where(Patent.project_id == project_id, Patent.patent_number == patent_number)
                    .values(
                        title=enriched_data.get("title", ""),
                        abstract=enriched_data.get("abstract", ""),
                        assignee=enriched_data.get("assignee", ""),
                        fetch_status="success",
                        structured_summary=enriched_data.get("structured_summary", {}),
                    )
                )
                await db.commit()

            # 2. Embedding Phase
            logger.info("Step 2: Saving to Qdrant embedding database...")
            await set_embed_status(project_id, patent_number, "embedding")
            async with EMBED_SEMAPHORE:
                await embed_patent(
                    patent_number=canonical_patent,
                    abstract_data=s_abstract,
                    claims_data=s_claims,
                    description_data=s_desc,
                    project_id=project_id,
                    user_id=user_id
                )

            # 3. Done
            logger.info("Step 3: Pipeline completed successfully.")
            await set_embed_status(project_id, patent_number, "done")
            return  # Exit the loop on success
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed for patent {patent_number}: {e}")
            if attempt < max_retries - 1:
                # Put it back to pending and wait 60 seconds before retrying
                await set_embed_status(project_id, patent_number, "pending")
                await asyncio.sleep(60)
            else:
                # Final failure after max retries
                await set_embed_status(project_id, patent_number, "failed")
                # Update Postgres on final failure
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

async def background_batch_embed(project_id: str, user_id: str, patent_numbers: list[str]):
    """
    Background task to run the pipeline for multiple patents concurrently.
    """
    if not patent_numbers:
        return

    # Set all to pending immediately
    for p in patent_numbers:
        await set_embed_status(project_id, p, "pending")
    
    # Fire off all pipelines concurrently (semaphores will throttle the actual work internally)
    tasks = [
        _pipeline_fetch_and_embed(project_id, user_id, p)
        for p in patent_numbers
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
