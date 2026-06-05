import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from sqlalchemy import text

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE claim_charts ADD COLUMN IF NOT EXISTS llm_score FLOAT DEFAULT 0.0;'))
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
