from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator

from app.core.config import settings
from sqlalchemy import event
import logging

db_logger = logging.getLogger("database.operations")

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    pool_size=20,
    max_overflow=30,
    pool_timeout=60.0,
    pool_recycle=300 # Automatically recycle idle connections every 5 minutes
)

@event.listens_for(engine.sync_engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """
    Intercepts every database query right before execution and logs if it's a fetch or store.
    The dynamic router will automatically tag this with the user/project context!
    """
    stmt = statement.strip().upper()
    if stmt.startswith("SELECT"):
        # Use debug for fetches so we don't flood the logs too heavily (can be info if preferred)
        db_logger.debug(f"[DB FETCH] Executing query: {statement[:150]}...")
    elif stmt.startswith("INSERT"):
        db_logger.info(f"[DB STORE] Inserting new record: {statement[:150]}...")
    elif stmt.startswith("UPDATE"):
        db_logger.info(f"[DB UPDATE] Modifying record: {statement[:150]}...")
    elif stmt.startswith("DELETE"):
        db_logger.warning(f"[DB DELETE] Removing record: {statement[:150]}...")

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
