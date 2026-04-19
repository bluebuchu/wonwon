import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from database import save_batch
from models import WeeklyBatch
from services.claude_engine import run_weekly_generation
from services.news_collector import collect_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cron", tags=["cron"])


@router.get("/generate")
async def cron_generate(authorization: str | None = Header(default=None)):
    """Called by Vercel Cron every Friday at 17:00 KST.

    Vercel automatically sends Authorization: Bearer $CRON_SECRET for cron jobs.
    Reference: https://vercel.com/docs/cron-jobs/manage-cron-jobs#securing-cron-jobs
    """
    cron_secret = os.getenv("CRON_SECRET", "")
    if not cron_secret:
        raise HTTPException(status_code=500, detail="CRON_SECRET is not configured on the server.")

    expected = f"Bearer {cron_secret}"
    if not authorization or authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized cron call.")

    logger.info(f"[Cron] Weekly generation triggered at {datetime.now(timezone.utc).isoformat()}")

    try:
        news_items = await collect_news()
        if not news_items:
            return {"status": "skipped", "reason": "no news items"}

        issue_packages = await run_weekly_generation(news_items)
        if not issue_packages:
            return {"status": "skipped", "reason": "no packages generated"}

        week_date = issue_packages[0].week_date
        batch = WeeklyBatch(
            week_date=week_date,
            issues=issue_packages,
            generated_at=datetime.now(timezone.utc),
        )
        await save_batch(batch)

        logger.info(f"[Cron] Saved {len(issue_packages)} issues for week {week_date}")
        return {"status": "success", "count": len(issue_packages), "week_date": week_date}

    except Exception as e:
        logger.error(f"[Cron] Failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
