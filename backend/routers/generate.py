import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth import verify_api_key
from database import get_batch_exists, save_batch
from models import GenerateResponse, WeeklyBatch
from services.claude_engine import run_weekly_generation
from services.news_collector import collect_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])

# Track ongoing generation to prevent duplicate runs (in-process guard only;
# not reliable across serverless invocations — see advisory lock plan for prod)
_generation_in_progress = False


async def _run_pipeline() -> tuple[int, str, str]:
    """
    Execute the full generation pipeline.
    Returns (issue_count, week_date, status).
    status: "success" | "partial_success" | "fallback" | "preserved_previous"
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

        # Step 2: Generate issue packages via Gemini (raw fallback 포함 가능)
        logger.info("[Generate] Generating issue packages via Gemini...")
        result = await run_weekly_generation(news_items)
        issue_packages = result.packages
        logger.info(
            f"[Generate] mode={result.mode} partial_success={result.partial_success} "
            f"generated={result.generated_count} failed={result.failed_count} "
            f"raw_fallback={result.raw_fallback_count} attempted={result.attempted}"
        )

        if not issue_packages:
            raise ValueError("No issue packages produced (AI failed and no raw fallback available)")

        # Step 3: Preservation guard — fallback이 기존 정상 배치를 덮어쓰지 않도록 보호
        week_date = issue_packages[0].week_date

        if result.mode == "raw_fallback":
            existing = await get_batch_exists(week_date)
            if existing:
                logger.info(
                    f"[Generate] preserved_previous: existing batch found for "
                    f"week={week_date}, skipping fallback save"
                )
                return 0, week_date, "preserved_previous"

        # Step 4: Save to database (정상/부분 성공, 또는 기존 배치 없는 fallback)
        batch = WeeklyBatch(
            week_date=week_date,
            issues=issue_packages,
            generated_at=datetime.now(timezone.utc),
        )
        await save_batch(batch)
        logger.info(
            f"[Generate] Saved batch for week {week_date} mode={result.mode} "
            f"generated={result.generated_count} failed={result.failed_count} "
            f"raw_fallback={result.raw_fallback_count}"
        )

        if result.mode == "raw_fallback":
            status = "fallback"
        elif result.partial_success:
            status = "partial_success"
        else:
            status = "success"

        return len(issue_packages), week_date, status

    finally:
        _generation_in_progress = False


_STATUS_MESSAGES = {
    "success": lambda count, _week: f"{count}개의 이슈 패키지가 정상 생성되어 저장되었습니다.",
    "partial_success": lambda count, _week: f"{count}개의 이슈 패키지가 저장되었습니다 (일부 AI 생성 실패).",
    "fallback": lambda count, _week: f"{count}개의 RSS 원문 카드가 저장되었습니다 (AI 생성 실패).",
    "preserved_previous": lambda _count, _week: "AI 생성 실패로 기존 정상 데이터를 유지했습니다.",
}


@router.post("/generate", response_model=GenerateResponse, dependencies=[Depends(verify_api_key)])
async def trigger_generation():
    """
    Manually trigger the full generation pipeline.

    This endpoint:
    1. Collects news from all configured Korean media RSS feeds
    2. Sends news to Gemini for clustering into 9 issue groups (3 per track)
    3. Generates [중] and [상] exploration topics for each issue
    4. Saves the complete batch to the database (unless fallback would overwrite existing data)

    Returns the number of generated issues and the week date.

    Note: This operation takes 1-3 minutes due to Gemini API calls.
    """
    global _generation_in_progress

    if _generation_in_progress:
        raise HTTPException(
            status_code=409,
            detail="A generation pipeline is already in progress. Please wait for it to complete.",
        )

    try:
        count, week_date, status = await _run_pipeline()
        message = _STATUS_MESSAGES.get(status, lambda c, w: f"status={status}")(count, week_date)
        return GenerateResponse(
            status=status,
            count=count,
            week_date=week_date,
            message=message,
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
