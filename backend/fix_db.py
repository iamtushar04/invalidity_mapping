import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def alter_tables():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("No DATABASE_URL found.")
        return
        
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        try:
            print("Adding columns to claim_elements...")
            await conn.execute(text("ALTER TABLE claim_elements ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE;"))
            await conn.execute(text("ALTER TABLE claim_elements ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;"))
            await conn.execute(text("ALTER TABLE claim_elements ADD COLUMN IF NOT EXISTS comment VARCHAR;"))
            await conn.execute(text("ALTER TABLE claim_elements ADD COLUMN IF NOT EXISTS is_custom BOOLEAN DEFAULT FALSE;"))
            print("claim_elements updated.")
        except Exception as e:
            print(f"Error on claim_elements: {e}")
            
        try:
            print("Fixing analysis_jobs schema issues...")
            await conn.execute(text("ALTER TABLE analysis_jobs ALTER COLUMN status TYPE VARCHAR USING status::text;"))
            await conn.execute(text("ALTER TABLE analysis_jobs ALTER COLUMN llm_anomaly_count DROP NOT NULL;"))
            await conn.execute(text("ALTER TABLE analysis_jobs ALTER COLUMN llm_hallucination_count DROP NOT NULL;"))
            print("analysis_jobs updated.")
        except Exception as e:
            print(f"Error on analysis_jobs: {e}")

        try:
            print("Adding columns to mappings...")
            await conn.execute(text("ALTER TABLE mappings ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE;"))
            await conn.execute(text("ALTER TABLE mappings ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;"))
            await conn.execute(text("ALTER TABLE mappings ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();"))
            # Note: mapping.py also has claim_id nullable=True, classification, etc. 
            # If any of those are missing, they should be added here too.
            print("mappings updated.")
        except Exception as e:
            print(f"Error on mappings: {e}")

if __name__ == "__main__":
    asyncio.run(alter_tables())
