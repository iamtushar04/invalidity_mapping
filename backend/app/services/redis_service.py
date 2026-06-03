import redis.asyncio as redis
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Initialize a global async Redis client pool
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

async def set_embed_status(project_id: str, patent_number: str, status: str):
    """
    Store the embed status for a patent in Redis.
    Keys are automatically expired.
    - If status is 'done', it expires in 24 hours (86400 seconds) so the UI can still show it.
    - If status is 'failed', it expires in 7 days (604800 seconds).
    - Otherwise (pending/fetching/embedding), it expires in 2 hours (in case it gets stuck).
    """
    key = f"embed:{project_id}:{patent_number}"
    try:
        if status == "done":
            ttl = 86400
        elif status == "failed":
            ttl = 604800
        else:
            ttl = 7200

        await redis_client.setex(key, ttl, status)
        logger.info(f"Set redis {key} = {status} (TTL: {ttl}s)")
    except Exception as e:
        logger.error(f"Failed to set redis status for {key}: {e}")

async def get_embed_status(project_id: str, patent_number: str) -> str | None:
    """
    Get the embed status for a single patent.
    """
    key = f"embed:{project_id}:{patent_number}"
    try:
        return await redis_client.get(key)
    except Exception as e:
        logger.error(f"Failed to get redis status for {key}: {e}")
        return None

async def get_all_embed_statuses(project_id: str, patent_numbers: list[str]) -> dict[str, str]:
    """
    Bulk fetch embed statuses for a list of patent numbers in a project.
    """
    if not patent_numbers:
        return {}
    
    keys = [f"embed:{project_id}:{p}" for p in patent_numbers]
    try:
        # mget returns a list of values in the same order as the keys
        values = await redis_client.mget(keys)
        return {p: v for p, v in zip(patent_numbers, values) if v is not None}
    except Exception as e:
        logger.error(f"Failed to mget redis statuses for project {project_id}: {e}")
        return {}
