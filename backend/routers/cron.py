import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from database import get_batch_exists, save_batch
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

    응답 상태 매트릭스:
      - success            : AI 전체 정상 생성·저장
      - partial_success    : AI 일부 성공, 일부 실패 (mode=normal)
      - fallback           : AI 전수 실패, 기존 배치 없음 → RSS 원문 저장
      - preserved_previous : AI 전수 실패, 기존 배치 있음 → 저장 생략, 기존 유지
      - failed             : 패키지 자체가 0건 (RSS + AI + fallback 모두 비어있는 극단 케이스)
      - skipped            : RSS 자체가 0건
      - 401                : 인증 실패
      - 500                : 환경변수 누락 / DB save 실패 (운영자 알림 신호)
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
    rss_collected = 0

    try:
        stage = "news"
        logger.info("[Cron][news] collecting RSS feeds")
        news_items = await collect_news()
        rss_collected = len(news_items)
        logger.info(f"[Cron][news] collected {rss_collected} items")

        if not news_items:
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.warning("[Cron][news] no items collected — skipping (RSS empty)")
            logger.info(
                f"[Cron][done] rss_collected=0 ai_generated=0 failed_count=0 "
                f"raw_fallback_count=0 existing_batch_found=False preserved_previous=False "
                f"save_attempted=False status=skipped elapsed={elapsed:.1f}s"
            )
            return {
                "status": "skipped",
                "reason": "no_news_items",
                "mode": None,
                "rss_collected": 0,
                "partial_success": False,
                "generated_count": 0,
                "failed_count": 0,
                "raw_fallback_count": 0,
                "failed_titles": [],
                "existing_batch_found": False,
                "preserved_previous": False,
                "save_attempted": False,
            }

        stage = "generate"
        logger.info(f"[Cron][generate] starting (input={rss_collected} items)")
        result = await run_weekly_generation(news_items)
        issue_packages = result.packages
        logger.info(
            f"[Cron][generate] mode={result.mode} partial_success={result.partial_success} "
            f"generated={result.generated_count} failed={result.failed_count} "
            f"raw_fallback={result.raw_fallback_count} attempted={result.attempted} "
            f"reason={result.reason} failed_titles={result.failed_titles}"
        )

        if not issue_packages:
            # raw fallback도 비어있는 극단 케이스 — RSS 비어있지 않은데 패키지 0건
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.warning(
                f"[Cron][generate] no packages and no raw fallback available "
                f"(reason={result.reason})"
            )
            logger.info(
                f"[Cron][done] rss_collected={rss_collected} ai_generated=0 "
                f"failed_count={result.failed_count} raw_fallback_count=0 "
                f"existing_batch_found=False preserved_previous=False save_attempted=False "
                f"status=failed elapsed={elapsed:.1f}s"
            )
            return {
                "status": "failed",
                "reason": result.reason or "no_packages_no_fallback",
                "mode": result.mode,
                "rss_collected": rss_collected,
                "partial_success": False,
                "generated_count": 0,
                "failed_count": result.failed_count,
                "raw_fallback_count": 0,
                "failed_titles": result.failed_titles,
                "existing_batch_found": False,
                "preserved_previous": False,
                "save_attempted": False,
            }

        stage = "save"
        week_date = issue_packages[0].week_date

        existing_batch_found = False
        preserved_previous = False
        save_attempted = False

        # Preservation guard: fallback이 기존 정상 배치를 덮어쓰지 않도록 보호
        if result.mode == "raw_fallback":
            existing_batch_found = await get_batch_exists(week_date)
            if existing_batch_found:
                preserved_previous = True
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                logger.info(
                    f"[Cron][save] preserved_previous: existing batch found for "
                    f"week={week_date}, skipping fallback save "
                    f"(ai_generated=0 raw_fallback={result.raw_fallback_count})"
                )
                logger.info(
                    f"[Cron][done] rss_collected={rss_collected} ai_generated=0 "
                    f"failed_count={result.failed_count} raw_fallback_count={result.raw_fallback_count} "
                    f"existing_batch_found=True preserved_previous=True save_attempted=False "
                    f"status=preserved_previous elapsed={elapsed:.1f}s"
                )
                return {
                    "status": "preserved_previous",
                    "mode": result.mode,
                    "week_date": week_date,
                    "rss_collected": rss_collected,
                    "partial_success": False,
                    "generated_count": 0,
                    "failed_count": result.failed_count,
                    "raw_fallback_count": result.raw_fallback_count,
                    "failed_titles": result.failed_titles,
                    "reason": result.reason,
                    "existing_batch_found": True,
                    "preserved_previous": True,
                    "save_attempted": False,
                }

        # 저장: 정상/부분 성공, 또는 기존 배치 없는 fallback 최초 저장
        batch = WeeklyBatch(
            week_date=week_date,
            issues=issue_packages,
            generated_at=datetime.now(timezone.utc),
        )
        save_attempted = True
        logger.info(
            f"[Cron][save] writing batch week_date={week_date} mode={result.mode} "
            f"generated={result.generated_count} failed={result.failed_count} "
            f"raw_fallback={result.raw_fallback_count}"
        )
        await save_batch(batch)

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

        if result.mode == "raw_fallback":
            status = "fallback"
        elif result.partial_success:
            status = "partial_success"
        else:
            status = "success"

        logger.info(
            f"[Cron][done] rss_collected={rss_collected} ai_generated={result.generated_count} "
            f"failed_count={result.failed_count} raw_fallback_count={result.raw_fallback_count} "
            f"existing_batch_found={existing_batch_found} preserved_previous=False "
            f"save_attempted=True status={status} elapsed={elapsed:.1f}s"
        )
        return {
            "status": status,
            "mode": result.mode,
            "week_date": week_date,
            "rss_collected": rss_collected,
            "partial_success": result.partial_success,
            "generated_count": result.generated_count,
            "failed_count": result.failed_count,
            "raw_fallback_count": result.raw_fallback_count,
            "failed_titles": result.failed_titles,
            "reason": result.reason,
            "existing_batch_found": existing_batch_found,
            "preserved_previous": False,
            "save_attempted": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        logger.error(
            f"[Cron][failed] stage={stage} elapsed={elapsed:.1f}s error={e}",
            exc_info=True,
        )
        # stage=generate는 raw fallback으로 흡수되므로 여기 도달하지 않는다.
        # 도달했다면 stage=news(예외적 케이스), stage=save(DB 장애), 또는 코드 버그.
        raise HTTPException(status_code=500, detail=f"stage={stage}: {e}")
