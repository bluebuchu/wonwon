import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from database import save_batch
from models import GenerateResponse, WeeklyBatch
from services.claude_engine import run_weekly_generation
from services.news_collector import collect_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])

# Track ongoing generation to prevent duplicate runs
_generation_in_progress = False


async def _run_pipeline() -> tuple[int, str]:
    """
    Execute the full generation pipeline.
    Returns (issue_count, week_date).
    """
    global _generation_in_progress
    _generation_in_progress = True

    try:
        # Step 1: Collect news from RSS feeds
        logger.info("[Generate] Collecting news from RSS feeds...")
        news_items = await collect_news()
        logger.info(f"[Generate] Collected {len(news_items)} news items")

        if not news_items:
            raise ValueError("No news items could be collected from RSS feeds")

        # Step 2: Generate issue packages via Claude
        logger.info("[Generate] Generating issue packages via Claude...")
        issue_packages = await run_weekly_generation(news_items)
        logger.info(f"[Generate] Generated {len(issue_packages)} issue packages")

        if not issue_packages:
            raise ValueError("Claude failed to generate any issue packages")

        # Step 3: Save to database
        week_date = issue_packages[0].week_date
        batch = WeeklyBatch(
            week_date=week_date,
            issues=issue_packages,
            generated_at=datetime.now(timezone.utc),
        )
        await save_batch(batch)
        logger.info(f"[Generate] Saved batch for week {week_date}")

        return len(issue_packages), week_date

    finally:
        _generation_in_progress = False


@router.post("/generate", response_model=GenerateResponse)
async def trigger_generation():
    """
    Manually trigger the full generation pipeline.

    This endpoint:
    1. Collects news from all configured Korean media RSS feeds
    2. Sends news to Claude for clustering into 9 issue groups (3 per track)
    3. Generates [중] and [상] exploration topics for each issue
    4. Saves the complete batch to the database

    Returns the number of generated issues and the week date.

    Note: This operation takes 1-3 minutes due to Claude API calls.
    """
    global _generation_in_progress

    if _generation_in_progress:
        raise HTTPException(
            status_code=409,
            detail="A generation pipeline is already in progress. Please wait for it to complete.",
        )

    try:
        count, week_date = await _run_pipeline()
        return GenerateResponse(
            status="success",
            count=count,
            week_date=week_date,
            message=f"{count}개의 이슈 패키지가 생성되어 저장되었습니다.",
        )
    except ValueError as e:
        logger.error(f"[Generate] Pipeline error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"[Generate] Unexpected pipeline error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Generation pipeline failed: {str(e)}",
        )
