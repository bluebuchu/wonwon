"""
Cron resilience tests — Gemini 장애 상황에서도 주간 발행이 유지되는지 검증.

stdlib(unittest) + unittest.mock만 사용 — pytest 의존성 없음. 실행:
    cd backend && python -m unittest tests.test_cron_resilience -v
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, patch

# backend/ 디렉터리를 sys.path에 추가 (config, models 등 직접 import 가능하도록)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 테스트에서 .env 없이도 모듈이 로드되도록 더미 값 주입
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("CRON_SECRET", "test-secret")

from models import IssuePackage, TrackType  # noqa: E402
from services.claude_engine import (  # noqa: E402
    WeeklyGenerationResult,
    _build_raw_fallback_packages,
    run_weekly_generation,
)


def _run(coro):
    """asyncio.run 단축."""
    return asyncio.run(coro)


def _sample_news(n: int = 12) -> List[dict]:
    """가짜 RSS items. published_at 내림차순 정렬 검증을 위해 의도적으로 뒤섞음."""
    base_dates = [
        "2026-05-22T10:00:00+00:00",  # newest
        "2026-05-21T09:00:00+00:00",
        "2026-05-22T15:00:00+00:00",  # actually newest
        "2026-05-20T12:00:00+00:00",
        "2026-05-22T08:00:00+00:00",
        "2026-05-19T11:00:00+00:00",
        "2026-05-22T20:00:00+00:00",  # newest of all
        "2026-05-18T11:00:00+00:00",
        None,  # missing date
        "2026-05-21T14:00:00+00:00",
        "2026-05-22T05:00:00+00:00",
        "2026-05-17T11:00:00+00:00",
    ]
    return [
        {
            "title": f"테스트 기사 {i+1}",
            "summary": f"요약 {i+1} — 정책/기술/교육 관련 내용",
            "url": f"https://example.com/{i+1}",
            "outlet": ["연합뉴스", "JTBC", "한겨레", "조선일보"][i % 4],
            "published_at": base_dates[i % len(base_dates)],
        }
        for i in range(n)
    ]


class TestRawFallbackBuilder(unittest.TestCase):
    """_build_raw_fallback_packages — 순수 함수, AI 호출 없음."""

    def test_builds_default_count(self):
        news = _sample_news(12)
        packages = _build_raw_fallback_packages(news, "2026-05-22")
        # RAW_FALLBACK_COUNT = 6
        self.assertEqual(len(packages), 6)

    def test_track_round_robin(self):
        news = _sample_news(6)
        packages = _build_raw_fallback_packages(news, "2026-05-22")
        # 0,1,2,3,4,5 → 인문/자연/의약/인문/자연/의약
        expected = [
            TrackType.humanities_social,
            TrackType.natural_engineering,
            TrackType.medical_life,
            TrackType.humanities_social,
            TrackType.natural_engineering,
            TrackType.medical_life,
        ]
        self.assertEqual([p.track for p in packages], expected)

    def test_sorted_by_published_at_desc(self):
        news = _sample_news(12)
        packages = _build_raw_fallback_packages(news, "2026-05-22")
        # 가장 새로운 published_at(=2026-05-22T20:00)을 가진 기사가 첫 번째여야 함
        # _sample_news는 index 6에 2026-05-22T20:00을 둠 ("테스트 기사 7")
        self.assertEqual(packages[0].title, "테스트 기사 7")

    def test_empty_news_returns_empty(self):
        self.assertEqual(_build_raw_fallback_packages([], "2026-05-22"), [])

    def test_packages_pass_pydantic_validation(self):
        news = _sample_news(6)
        packages = _build_raw_fallback_packages(news, "2026-05-22")
        for pkg in packages:
            # IssuePackage가 만들어졌다는 자체가 Pydantic 통과
            self.assertIsInstance(pkg, IssuePackage)
            # placeholder reason 길이 ≥30 (min_length 통과 확인)
            self.assertGreaterEqual(len(pkg.mid_topic.reason), 30)
            self.assertGreaterEqual(len(pkg.high_topic.reason), 30)
            # placeholder 식별 문구 포함
            self.assertIn("AI 분석 서비스 장애", pkg.mid_topic.reason)
            # 사용자가 식별 가능한 raw 모드 마커
            self.assertIn("원문 뉴스", pkg.mid_topic.topic)

    def test_missing_published_at_treated_as_oldest(self):
        news = [
            {"title": "no date", "url": "u1", "outlet": "o1", "summary": "s", "published_at": None},
            {"title": "with date", "url": "u2", "outlet": "o2", "summary": "s",
             "published_at": "2026-05-22T10:00:00+00:00"},
        ]
        packages = _build_raw_fallback_packages(news, "2026-05-22", n=2)
        # 날짜 있는 것이 먼저
        self.assertEqual(packages[0].title, "with date")
        self.assertEqual(packages[1].title, "no date")


class TestRunWeeklyGenerationClusteringFailure(unittest.TestCase):
    """Clustering 실패 → raw_fallback 모드로 전환."""

    def test_clustering_503_returns_raw_fallback(self):
        news = _sample_news(10)
        with patch(
            "services.claude_engine.cluster_and_tag_issues",
            new_callable=AsyncMock,
            side_effect=Exception("503 UNAVAILABLE"),
        ):
            result: WeeklyGenerationResult = _run(run_weekly_generation(news))

        self.assertEqual(result.mode, "raw_fallback")
        self.assertEqual(result.reason, "clustering_failed")
        self.assertEqual(result.generated_count, 0)
        self.assertEqual(result.raw_fallback_count, 6)
        self.assertEqual(len(result.packages), 6)
        self.assertFalse(result.partial_success)  # raw_fallback은 partial_success=False
        self.assertEqual(result.failed_titles, [])

    def test_clustering_empty_returns_raw_fallback(self):
        news = _sample_news(10)
        with patch(
            "services.claude_engine.cluster_and_tag_issues",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = _run(run_weekly_generation(news))

        self.assertEqual(result.mode, "raw_fallback")
        self.assertEqual(result.reason, "clustering_empty")
        self.assertEqual(result.raw_fallback_count, 6)


class TestRunWeeklyGenerationAllIssuesFailure(unittest.TestCase):
    """Clustering OK, per-issue 9건 모두 실패 → raw_fallback 강등."""

    def test_all_issues_503_returns_raw_fallback(self):
        news = _sample_news(10)
        clustered = [
            {"track": "인문사회", "title": f"issue {i}", "summary": "s",
             "keywords": [], "sources": []}
            for i in range(9)
        ]
        with patch(
            "services.claude_engine.cluster_and_tag_issues",
            new_callable=AsyncMock, return_value=clustered,
        ), patch(
            "services.claude_engine._generate_validated_package",
            new_callable=AsyncMock,
            side_effect=Exception("503 UNAVAILABLE"),
        ):
            result = _run(run_weekly_generation(news))

        self.assertEqual(result.mode, "raw_fallback")
        self.assertEqual(result.reason, "all_issues_failed")
        self.assertEqual(result.generated_count, 0)
        self.assertEqual(result.failed_count, 9)
        self.assertEqual(result.raw_fallback_count, 6)
        self.assertEqual(result.attempted, 9)
        self.assertEqual(len(result.failed_titles), 9)
        self.assertFalse(result.partial_success)


class TestRunWeeklyGenerationPartialSuccess(unittest.TestCase):
    """Clustering OK, per-issue 9건 중 4건 성공 → mode=normal, partial_success=True."""

    def test_partial_success_marks_partial(self):
        news = _sample_news(10)
        clustered = [
            {"track": ["인문사회", "자연공학", "의약생명"][i % 3],
             "title": f"issue {i}", "summary": "structural summary",
             "keywords": ["k1", "k2", "k3"],
             "sources": [{"outlet": "o", "url": "https://x"}]}
            for i in range(9)
        ]

        async def flaky_validate(issue):
            # 짝수 index는 성공, 홀수는 503 — 9건 중 5건 성공
            # (테스트 단순화를 위해 success_pkg는 _build_issue_package 입력으로 그대로 사용)
            # _generate_validated_package는 raw dict를 반환하므로 그것을 흉내냄
            idx = int(issue["title"].split()[-1])
            if idx % 2 == 1:
                raise Exception("503 UNAVAILABLE")
            return {
                "mid_topic": {
                    "topic": "탐구질문 중급",
                    "reason": "이 주제는 학생들이 사회적 맥락에서 현상의 원인을 구조적으로 "
                              "분석하고 비판적 사고를 키우는 데 적합한 학문적 가치가 있다. "
                              "관련 학문 방법론을 적용해보는 좋은 사례.",
                    "grade_guide": {"grade1": "기초 조사",
                                    "grade2": "심화 분석",
                                    "grade3": "독자적 가설"},
                    "level": "중",
                },
                "high_topic": {
                    "topic": "탐구질문 고급",
                    "reason": "이 주제는 융합적 사고와 창의적 접근이 필요한 심화 탐구로 "
                              "기존 연구를 비판적으로 평가하고 독창적 가설을 제시할 수 있는 "
                              "학문적 깊이를 가진다. 학생의 비판력을 키운다.",
                    "grade_guide": {"grade1": "관찰",
                                    "grade2": "비교 연구",
                                    "grade3": "논증"},
                    "level": "상",
                },
            }

        with patch(
            "services.claude_engine.cluster_and_tag_issues",
            new_callable=AsyncMock, return_value=clustered,
        ), patch(
            "services.claude_engine._generate_validated_package",
            side_effect=flaky_validate,
        ):
            result = _run(run_weekly_generation(news))

        self.assertEqual(result.mode, "normal")
        self.assertTrue(result.partial_success)
        # 9건 중 짝수 index 0,2,4,6,8 = 5건 성공, 홀수 1,3,5,7 = 4건 실패
        self.assertEqual(result.generated_count, 5)
        self.assertEqual(result.failed_count, 4)
        self.assertEqual(result.raw_fallback_count, 0)
        self.assertEqual(result.attempted, 9)
        self.assertEqual(len(result.failed_titles), 4)
        # status는 cron.py에서 partial_success bool을 보고 "partial_success" 문자열로 변환


class TestCronEndpointHTTPContract(unittest.TestCase):
    """cron_generate 핸들러의 응답 구조 — HTTPException 발생/미발생 검증."""

    def setUp(self):
        os.environ["CRON_SECRET"] = "test-secret"

    def _call(self, news_items, gen_result):
        from routers.cron import cron_generate

        async def runner():
            with patch(
                "routers.cron.collect_news",
                new_callable=AsyncMock, return_value=news_items,
            ), patch(
                "routers.cron.run_weekly_generation",
                new_callable=AsyncMock, return_value=gen_result,
            ), patch(
                "routers.cron.save_batch",
                new_callable=AsyncMock,
            ) as mock_save:
                resp = await cron_generate(authorization="Bearer test-secret")
                return resp, mock_save
        return _run(runner())

    def _fake_package(self, week_date="2026-05-22") -> IssuePackage:
        from services.claude_engine import _build_raw_fallback_packages
        # 가짜 RSS 1개로 raw 1개 만들어 IssuePackage 인스턴스 확보
        items = [{
            "title": "fake", "summary": "fake summary",
            "url": "https://x", "outlet": "o",
            "published_at": "2026-05-22T10:00:00+00:00",
        }]
        return _build_raw_fallback_packages(items, week_date, n=1)[0]

    def test_raw_fallback_response_is_200_with_status_success(self):
        from services.claude_engine import _build_raw_fallback_packages
        news = _sample_news(10)
        raw_packages = _build_raw_fallback_packages(news, "2026-05-22")
        gen_result = WeeklyGenerationResult(
            packages=raw_packages, mode="raw_fallback",
            generated_count=0, failed_count=0, raw_fallback_count=6,
            attempted=0, failed_titles=[], reason="clustering_failed",
        )

        resp, mock_save = self._call(news, gen_result)
        self.assertEqual(resp["status"], "success")  # raw fallback도 status=success
        self.assertEqual(resp["mode"], "raw_fallback")
        self.assertEqual(resp["raw_fallback_count"], 6)
        self.assertEqual(resp["reason"], "clustering_failed")
        self.assertFalse(resp["partial_success"])
        # DB save 호출 검증
        mock_save.assert_awaited_once()

    def test_partial_success_status_is_partial_success(self):
        gen_result = WeeklyGenerationResult(
            packages=[self._fake_package()],
            mode="normal", generated_count=4, failed_count=5,
            raw_fallback_count=0, attempted=9,
            failed_titles=["a", "b", "c", "d", "e"], reason=None,
        )
        news = _sample_news(10)
        resp, mock_save = self._call(news, gen_result)
        self.assertEqual(resp["status"], "partial_success")
        self.assertEqual(resp["mode"], "normal")
        self.assertTrue(resp["partial_success"])
        self.assertEqual(resp["generated_count"], 4)
        self.assertEqual(resp["failed_count"], 5)
        self.assertEqual(len(resp["failed_titles"]), 5)
        mock_save.assert_awaited_once()

    def test_full_success_status_is_success(self):
        gen_result = WeeklyGenerationResult(
            packages=[self._fake_package()],
            mode="normal", generated_count=9, failed_count=0,
            raw_fallback_count=0, attempted=9,
            failed_titles=[], reason=None,
        )
        news = _sample_news(10)
        resp, mock_save = self._call(news, gen_result)
        self.assertEqual(resp["status"], "success")
        self.assertEqual(resp["mode"], "normal")
        self.assertFalse(resp["partial_success"])
        mock_save.assert_awaited_once()

    def test_rss_empty_returns_skipped_without_save(self):
        from routers.cron import cron_generate

        async def runner():
            with patch(
                "routers.cron.collect_news",
                new_callable=AsyncMock, return_value=[],
            ), patch(
                "routers.cron.save_batch", new_callable=AsyncMock,
            ) as mock_save:
                resp = await cron_generate(authorization="Bearer test-secret")
                return resp, mock_save

        resp, mock_save = _run(runner())
        self.assertEqual(resp["status"], "skipped")
        self.assertEqual(resp["reason"], "no_news_items")
        mock_save.assert_not_awaited()

    def test_unauthorized_raises_401(self):
        from fastapi import HTTPException
        from routers.cron import cron_generate

        with self.assertRaises(HTTPException) as ctx:
            _run(cron_generate(authorization="Bearer wrong"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_db_save_failure_raises_500(self):
        from fastapi import HTTPException
        from routers.cron import cron_generate

        gen_result = WeeklyGenerationResult(
            packages=[self._fake_package()],
            mode="normal", generated_count=9, failed_count=0,
            raw_fallback_count=0, attempted=9,
            failed_titles=[], reason=None,
        )

        async def runner():
            with patch(
                "routers.cron.collect_news",
                new_callable=AsyncMock, return_value=_sample_news(5),
            ), patch(
                "routers.cron.run_weekly_generation",
                new_callable=AsyncMock, return_value=gen_result,
            ), patch(
                "routers.cron.save_batch",
                new_callable=AsyncMock,
                side_effect=Exception("connection refused"),
            ):
                return await cron_generate(authorization="Bearer test-secret")

        with self.assertRaises(HTTPException) as ctx:
            _run(runner())
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("stage=save", ctx.exception.detail)


class TestRetryAttemptsReduced(unittest.TestCase):
    """retry attempts가 3으로 줄었는지 상수 확인."""

    def test_retry_attempts_is_3(self):
        from services.claude_engine import _RETRY_MAX_ATTEMPTS
        self.assertEqual(_RETRY_MAX_ATTEMPTS, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
