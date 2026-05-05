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

    started_at = datetime.now(timezone.utc)
    logger.info(f"[Cron] Weekly generation triggered at {started_at.isoformat()}")

    stage = "init"
    try:
        stage = "news"
        logger.info("[Cron][news] collecting RSS feeds")
        news_items = await collect_news()
        logger.info(f"[Cron][news] collected {len(news_items)} items")
        if not news_items:
            logger.warning("[Cron][news] no items collected — skipping generation")
            return {"status": "skipped", "reason": "no news items"}

        stage = "generate"
        logger.info(f"[Cron][generate] starting (input={len(news_items)} items)")
        issue_packages = await run_weekly_generation(news_items)
        logger.info(f"[Cron][generate] produced {len(issue_packages)} packages")
        if not issue_packages:
            # run_weekly_generation에서 임계치 미달 시 ValueError를 던지므로 일반적으로
            # 여기 도달하지 않지만 방어적으로 남겨둔다.
            logger.warning("[Cron][generate] empty package list — skipping save")
            return {"status": "skipped", "reason": "no packages generated"}

        stage = "save"
        week_date = issue_packages[0].week_date
        batch = WeeklyBatch(
            week_date=week_date,
            issues=issue_packages,
            generated_at=datetime.now(timezone.utc),
        )
        logger.info(f"[Cron][save] writing batch week_date={week_date} count={len(issue_packages)}")
        await save_batch(batch)

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        logger.info(
            f"[Cron][done] saved {len(issue_packages)} issues for week {week_date} "
            f"(elapsed={elapsed:.1f}s)"
        )
        return {"status": "success", "count": len(issue_packages), "week_date": week_date}

    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        logger.error(
            f"[Cron][failed] stage={stage} elapsed={elapsed:.1f}s error={e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"stage={stage}: {e}")
