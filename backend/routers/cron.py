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

    응답 매트릭스:
      - 200 success           : AI 전체 성공
      - 200 partial_success   : AI 일부 성공 (mode=normal, failed_titles 있음)
      - 200 success (raw)     : AI 전수 실패 → RSS 원문으로 강등 발행 (mode=raw_fallback)
      - 200 skipped           : RSS 자체가 0건 (발행할 게 없음)
      - 401                   : 인증 실패
      - 500                   : 환경변수 누락 / DB save 실패 (운영자 알림 신호)
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
            logger.warning("[Cron][news] no items collected — skipping (RSS empty)")
            return {
                "status": "skipped",
                "reason": "no_news_items",
                "mode": None,
                "partial_success": False,
                "generated_count": 0,
                "failed_count": 0,
                "raw_fallback_count": 0,
                "failed_titles": [],
            }

        stage = "generate"
        logger.info(f"[Cron][generate] starting (input={len(news_items)} items)")
        result = await run_weekly_generation(news_items)
        issue_packages = result.packages
        logger.info(
            f"[Cron][generate] mode={result.mode} partial_success={result.partial_success} "
            f"generated={result.generated_count} failed={result.failed_count} "
            f"raw_fallback={result.raw_fallback_count} attempted={result.attempted} "
            f"reason={result.reason} failed_titles={result.failed_titles}"
        )

        if not issue_packages:
            # raw fallback도 비어있는 케이스 — RSS가 어떤 이유로 0건이 된 후 raw 생성에서도 0개.
            # collect_news()의 0건 검사를 이미 통과했으므로 정상 흐름에선 도달하지 않는다.
            logger.warning(
                f"[Cron][generate] no packages and no raw fallback available "
                f"(reason={result.reason})"
            )
            return {
                "status": "skipped",
                "reason": result.reason or "no_packages_no_fallback",
                "mode": result.mode,
                "partial_success": False,
                "generated_count": 0,
                "failed_count": result.failed_count,
                "raw_fallback_count": 0,
                "failed_titles": result.failed_titles,
            }

        stage = "save"
        week_date = issue_packages[0].week_date
        batch = WeeklyBatch(
            week_date=week_date,
            issues=issue_packages,
            generated_at=datetime.now(timezone.utc),
        )
        logger.info(
            f"[Cron][save] writing batch week_date={week_date} mode={result.mode} "
            f"generated={result.generated_count} failed={result.failed_count} "
            f"raw_fallback={result.raw_fallback_count}"
        )
        await save_batch(batch)

        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        status = "partial_success" if result.partial_success else "success"
        logger.info(
            f"[Cron][done] status={status} mode={result.mode} week={week_date} "
            f"generated={result.generated_count} failed={result.failed_count} "
            f"raw_fallback={result.raw_fallback_count} elapsed={elapsed:.1f}s"
        )
        return {
            "status": status,                                # "success" | "partial_success"
            "mode": result.mode,                             # "normal" | "raw_fallback"
            "week_date": week_date,
            "partial_success": result.partial_success,
            "generated_count": result.generated_count,
            "failed_count": result.failed_count,
            "raw_fallback_count": result.raw_fallback_count,
            "failed_titles": result.failed_titles,
            "reason": result.reason,
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
        # 운영자 알림이 필요한 진짜 장애이므로 500을 유지한다.
        raise HTTPException(status_code=500, detail=f"stage={stage}: {e}")
