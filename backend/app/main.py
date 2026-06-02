from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logger import setup_logger, current_project_id
setup_logger()

from app.core.config import settings
from app.database import engine, Base
from app.api.routes import auth, projects, patents, claims, prior_art, analysis, export

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set all CORS enabled origins (allow frontend next.js access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to frontend domain
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProjectContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract potential UUID from URL path
        project_id = None
        for part in request.url.path.split('/'):
            if len(part) == 36 and part.count('-') == 4:
                project_id = part
                break
        
        # Reset context on every request to avoid leakage between async requests
        current_project_id.set(project_id)
        return await call_next(request)

app.add_middleware(ProjectContextMiddleware)

@app.on_event("startup")
async def on_startup():
    # Asynchronously create all database tables on startup
    import app.models # Ensure all models are loaded in Base metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Register routers
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["Authentication"])
app.include_router(projects.router, prefix=f"{settings.API_V1_STR}/projects", tags=["Projects"])
app.include_router(patents.router, prefix=f"{settings.API_V1_STR}/patents", tags=["Patents"])
app.include_router(claims.router, prefix=f"{settings.API_V1_STR}/claims", tags=["Claims & Elements"])
app.include_router(prior_art.router, prefix=f"{settings.API_V1_STR}/prior-art", tags=["Prior Art"])
app.include_router(analysis.router, prefix=f"{settings.API_V1_STR}/analysis", tags=["Obviousness Analysis"])
app.include_router(export.router, prefix=f"{settings.API_V1_STR}/charts", tags=["Chart Generation & Export"])

from fastapi import Response

@app.get("/health", tags=["Health"])
async def health_check(response: Response):
    import asyncio
    from sqlalchemy import text
    import redis.asyncio as aioredis
    import httpx
    from app.embedding.qdrant_service import _CLIENT

    health_status = {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "dependencies": {}
    }
    
    # 1. Postgres Check
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            health_status["dependencies"]["postgres"] = "ok"
    except Exception as e:
        health_status["dependencies"]["postgres"] = f"down: {str(e)}"
        health_status["status"] = "degraded"

    # 2. Redis Check
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL)
        # pyrefly: ignore [not-async]
        await redis_client.ping()
        await redis_client.aclose()
        health_status["dependencies"]["redis"] = "ok"
    except Exception as e:
        health_status["dependencies"]["redis"] = f"down: {str(e)}"
        health_status["status"] = "degraded"

    # 3. Qdrant Check
    try:
        await asyncio.to_thread(_CLIENT.get_collections)
        health_status["dependencies"]["qdrant"] = "ok"
    except Exception as e:
        health_status["dependencies"]["qdrant"] = f"down: {str(e)}"
        health_status["status"] = "degraded"
        
    # 4. OpenAI Check
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
            )
            if res.status_code == 200:
                health_status["dependencies"]["openai"] = "ok"
            else:
                health_status["dependencies"]["openai"] = f"degraded: HTTP {res.status_code}"
                health_status["status"] = "degraded"
    except Exception as e:
        health_status["dependencies"]["openai"] = f"down: {str(e)}"
        health_status["status"] = "degraded"

    if health_status["status"] == "degraded":
        response.status_code = 503

    return health_status
