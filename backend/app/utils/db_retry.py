import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, DBAPIError

logger = logging.getLogger(__name__)


async def commit_with_retry(db: AsyncSession, max_attempts: int = 3, wait_seconds: float = 3.0) -> None:
    """
    Commits the current SQLAlchemy session with automatic retry on transient DB errors.
    Retries up to `max_attempts` times with `wait_seconds` between each attempt.
    On final failure, the original exception is re-raised so existing error handlers catch it normally.
    """
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            await db.commit()
            return  # Success — exit immediately
        except (OperationalError, DBAPIError) as exc:
            last_err = exc
            logger.warning(
                "DB commit failed (attempt %d/%d): %s. %s",
                attempt,
                max_attempts,
                exc,
                "Retrying..." if attempt < max_attempts else "Giving up.",
            )
            if attempt < max_attempts:
                await asyncio.sleep(wait_seconds)
            else:
                raise last_err from exc
