from __future__ import annotations
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    SCHEDULER_DAY_OF_WEEK,
    SCHEDULER_HOUR,
    SCHEDULER_MINUTE,
    SCHEDULER_TIMEZONE,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_generation_pipeline() -> None:
    """
    Full generation pipeline: collect news → generate packages → save to DB.
    Called by scheduler every Friday at 17:00 KST.
    """
    from services.news_collector import collect_news
    from services.claude_engine import run_weekly_generation
    from database import save_batch
    from models import WeeklyBatch

    logger.info(f"[Scheduler] Starting weekly generation pipeline at {datetime.now(timezone.utc).isoformat()}")

    try:
        # Step 1: Collect news
        logger.info("[Scheduler] Collecting news from RSS feeds...")
        news_items = await collect_news()
        logger.info(f"[Scheduler] Collected {len(news_items)} news items")

        if not news_items:
            logger.warning("[Scheduler] No news items collected; aborting generation")
            return

        # Step 2: Generate issue packages via Claude
        logger.info("[Scheduler] Generating issue packages via Claude...")
        issue_packages = await run_weekly_generation(news_items)
        logger.info(f"[Scheduler] Generated {len(issue_packages)} issue packages")

        if not issue_packages:
            logger.warning("[Scheduler] No issue packages generated; aborting save")
            return

        # Step 3: Save to database
        week_date = issue_packages[0].week_date
        batch = WeeklyBatch(
            week_date=week_date,
            issues=issue_packages,
            generated_at=datetime.now(timezone.utc),
        )
        await save_batch(batch)
        logger.info(
            f"[Scheduler] Saved batch for week {week_date} "
            f"with {len(issue_packages)} issues"
        )

    except Exception as e:
        logger.error(f"[Scheduler] Pipeline failed: {e}", exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)

    trigger = CronTrigger(
        day_of_week=SCHEDULER_DAY_OF_WEEK,
        hour=SCHEDULER_HOUR,
        minute=SCHEDULER_MINUTE,
        timezone=SCHEDULER_TIMEZONE,
    )

    scheduler.add_job(
        run_generation_pipeline,
        trigger=trigger,
        id="weekly_generation",
        name="Weekly issue generation pipeline",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow up to 1 hour late execution
    )

    logger.info(
        f"Scheduler configured: every {SCHEDULER_DAY_OF_WEEK} at "
        f"{SCHEDULER_HOUR:02d}:{SCHEDULER_MINUTE:02d} {SCHEDULER_TIMEZONE}"
    )
    return scheduler


def start_scheduler() -> AsyncIOScheduler:
    """Create and start the scheduler. Returns the scheduler instance."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler is already running")
        return _scheduler

    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info("Scheduler started")
    return _scheduler


def stop_scheduler() -> None:
    """Stop the scheduler if running."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the current scheduler instance."""
    return _scheduler
