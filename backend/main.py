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
    await init_db()
    logger.info("Database initialized")

    # Start scheduler only in non-serverless environments
    if not os.getenv("VERCEL"):
        scheduler = start_scheduler()
        logger.info("Scheduler started")

    yield

    # Shutdown
    if not os.getenv("VERCEL"):
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
    from services.scheduler import get_scheduler

    scheduler = get_scheduler()
    scheduler_running = scheduler is not None and scheduler.running

    next_run = None
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
