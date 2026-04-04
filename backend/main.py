import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from routers.cron import router as cron_router
from routers.generate import router as generate_router
from routers.issues import router as issues_router
from routers.mock import router as mock_router
IS_VERCEL = bool(os.getenv("VERCEL"))

if not IS_VERCEL:
    from services.scheduler import start_scheduler, stop_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic."""
    logger.info("Starting Korean High School Exploration Topic Service...")

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database init failed (non-fatal): {e}")

    # Start scheduler only in non-serverless environments
    if not IS_VERCEL:
        scheduler = start_scheduler()
        logger.info("Scheduler started")

    yield

    # Shutdown
    if not IS_VERCEL:
        stop_scheduler()
        logger.info("Scheduler stopped")


app = FastAPI(
    title="Korean High School Exploration Topic Service",
    description=(
        "고등학생 탐구활동 주제 생성 서비스 API. "
        "매주 국내 뉴스를 수집하고 Claude AI를 활용하여 "
        "계열별 탐구 주제 패키지를 생성한다."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(issues_router)
app.include_router(generate_router)
app.include_router(mock_router)
app.include_router(cron_router)


@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint."""
    scheduler_running = False
    next_run = None

    if not IS_VERCEL:
        from services.scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler_running = scheduler is not None and scheduler.running
        if scheduler_running:
            jobs = scheduler.get_jobs()
            if jobs:
                next_fire = jobs[0].next_run_time
                next_run = next_fire.isoformat() if next_fire else None

    return {
        "status": "healthy",
        "service": "Korean High School Exploration Topic Service",
        "scheduler_running": scheduler_running,
        "next_generation": next_run,
    }


@app.get("/api/debug", tags=["system"])
async def debug():
    """Debug endpoint to check imports and env."""
    import sys
    info = {"version": "v7", "python": sys.version, "path": sys.path[:5], "env": {}}

    # Check env vars
    info["env"]["DATABASE_URL"] = bool(os.getenv("DATABASE_URL"))
    info["env"]["GOOGLE_API_KEY"] = bool(os.getenv("GOOGLE_API_KEY"))
    info["env"]["VERCEL"] = os.getenv("VERCEL", "not set")

    # Check imports
    imports = {}
    for mod in ["asyncpg", "feedparser", "google.genai", "pydantic", "pydantic_settings"]:
        try:
            __import__(mod)
            imports[mod] = "ok"
        except Exception as e:
            imports[mod] = str(e)
    info["imports"] = imports

    # Check DB URL parsing step by step
    import socket
    import re
    db_url = settings.database_url
    info["db_url_len"] = len(db_url)
    info["db_url_prefix"] = db_url[:30] + "..."

    # Manual regex parse to avoid any urlparse issues
    m = re.match(r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_url)
    if m:
        info["db_parsed"] = {
            "user": m.group(1)[:15] + "...",
            "host": m.group(3),
            "port": int(m.group(4)),
            "database": m.group(5),
        }
        host = m.group(3)
        try:
            resolved = socket.getaddrinfo(host, None)[0][4][0]
            info["db_dns"] = resolved
        except Exception as e:
            info["db_dns"] = f"failed: {e}"
    else:
        info["db_parsed"] = "regex no match"

    # Check DB connection
    try:
        from database import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
            info["db"] = f"connected (test={val})"
    except Exception as e:
        info["db"] = f"error: {e}"

    return info


@app.get("/", tags=["system"])
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Korean High School Exploration Topic Service",
        "version": "1.0.0",
        "description": "고등학생 계열별 탐구 주제 생성 API",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "issues": "/api/issues",
            "issue_detail": "/api/issues/{id}",
            "latest_issues": "/api/issues/latest",
            "weeks": "/api/weeks",
            "generate": "POST /api/generate",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
