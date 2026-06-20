"""
전역 호출 간격 제어 · 429 RetryInfo · 503/429 통합 재시도 테스트.

실행: cd backend && python -m unittest tests.test_rate_limit -v
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("CRON_SECRET", "test-secret")

import services.claude_engine as engine  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 테스트용 가짜 예외 — 실제 HTTP 스택 없이 코드 경로만 검증
# ---------------------------------------------------------------------------

class _Fake429(Exception):
    """429 RESOURCE_EXHAUSTED 모사."""
    code = 429
    status_code = 429
    status = "RESOURCE_EXHAUSTED"
    retry_delay = None
    details = []

    def __init__(self, retry_delay=None, msg="429 resource exhausted quota exceeded"):
        super().__init__(msg)
        self.retry_delay = retry_delay


class _Fake503(Exception):
    """503 UNAVAILABLE 모사."""
    code = 503
    status_code = 503
    status = "UNAVAILABLE"
    details = []

    def __init__(self, msg="503 Service Unavailable"):
        super().__init__(msg)


def _make_client(*side_effects):
    """generate_content 를 순서대로 raise/return 하는 mock client."""
    client = MagicMock()
    client.models.generate_content = MagicMock(side_effect=list(side_effects))
    return client


def _make_config():
    from google.genai import types
    return MagicMock(spec=types.GenerateContentConfig)


def _patch_rate_gate():
    """rate gate를 no-op AsyncMock으로 교체 (실제 15s 대기 없음)."""
    return patch("services.claude_engine._wait_for_rate_limit", new_callable=AsyncMock)


def _patch_sleep():
    """asyncio.sleep을 기록 전용 mock으로 교체."""
    slept: list[float] = []

    async def _fake_sleep(n: float) -> None:
        slept.append(n)

    return patch("asyncio.sleep", side_effect=_fake_sleep), slept


# ===========================================================================
# 1. _is_rate_limit_error
# ===========================================================================

class TestIsRateLimitError(unittest.TestCase):

    def test_fake429_detected(self):
        self.assertTrue(engine._is_rate_limit_error(_Fake429()))

    def test_resource_exhausted_status(self):
        exc = Exception("some error")
        exc.code = 200
        exc.status = "RESOURCE_EXHAUSTED"
        self.assertTrue(engine._is_rate_limit_error(exc))

    def test_429_in_message(self):
        self.assertTrue(engine._is_rate_limit_error(Exception("HTTP 429 too many")))

    def test_quota_exceeded_in_message(self):
        self.assertTrue(engine._is_rate_limit_error(Exception("quota exceeded")))

    def test_rate_limit_in_message(self):
        self.assertTrue(engine._is_rate_limit_error(Exception("rate limit hit")))

    def test_fake503_not_rate_limit(self):
        self.assertFalse(engine._is_rate_limit_error(_Fake503()))

    def test_json_error_not_rate_limit(self):
        self.assertFalse(engine._is_rate_limit_error(ValueError("invalid json")))

    def test_500_not_rate_limit(self):
        exc = Exception("500 internal error")
        self.assertFalse(engine._is_rate_limit_error(exc))


# ===========================================================================
# 2. _extract_429_retry_delay
# ===========================================================================

class TestExtract429RetryDelay(unittest.TestCase):

    def test_timedelta_attribute(self):
        exc = _Fake429(retry_delay=timedelta(seconds=45))
        self.assertAlmostEqual(engine._extract_429_retry_delay(exc), 45.0)

    def test_float_attribute(self):
        exc = _Fake429(retry_delay=30.5)
        self.assertAlmostEqual(engine._extract_429_retry_delay(exc), 30.5)

    def test_int_attribute(self):
        exc = _Fake429(retry_delay=20)
        self.assertAlmostEqual(engine._extract_429_retry_delay(exc), 20.0)

    def test_grpc_retry_info_in_details(self):
        exc = _Fake429()
        exc.retry_delay = None
        detail = MagicMock()
        detail.retry_delay = MagicMock()
        detail.retry_delay.seconds = 60
        detail.retry_delay.nanos = 500_000_000  # 0.5s
        exc.details = [detail]
        result = engine._extract_429_retry_delay(exc)
        self.assertAlmostEqual(result, 60.5)

    def test_message_pattern_integer(self):
        exc = Exception("retry after 45s please wait")
        self.assertAlmostEqual(engine._extract_429_retry_delay(exc), 45.0)

    def test_message_pattern_float(self):
        exc = Exception("retry after 12.5s")
        self.assertAlmostEqual(engine._extract_429_retry_delay(exc), 12.5)

    def test_no_retry_info_returns_none(self):
        exc = _Fake429()
        self.assertIsNone(engine._extract_429_retry_delay(exc))

    def test_invalid_retry_delay_type_falls_through(self):
        exc = _Fake429(retry_delay="bad")
        # float("bad") raises ValueError → falls through to details/message
        result = engine._extract_429_retry_delay(exc)
        self.assertIsNone(result)


# ===========================================================================
# 3. _wait_for_rate_limit
# ===========================================================================

class TestWaitForRateLimit(unittest.TestCase):
    """_wait_for_rate_limit 테스트.
    time.monotonic을 전역 패치하면 asyncio 내부와 충돌하므로 실시간 타이머를 사용한다."""

    def setUp(self):
        engine._last_call_start = 0.0

    def test_no_sleep_when_enough_time_passed(self):
        """min_interval 이상 경과 시 sleep 없이 통과."""
        import time as _t
        # 마지막 호출이 min_interval + 1초 전에 있었던 것으로 설정
        engine._last_call_start = _t.monotonic() - (engine._GEMINI_MIN_INTERVAL + 1.0)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            _run(engine._wait_for_rate_limit("test"))
            mock_sleep.assert_not_called()

    def test_sleeps_for_approximate_deficit(self):
        """간격이 부족하면 부족분(≈10s)을 sleep."""
        import time as _t
        engine._last_call_start = _t.monotonic() - 5.0  # 5s 전 호출 → 10s 더 필요

        slept = []

        async def fake_sleep(n):
            slept.append(n)

        with patch("asyncio.sleep", side_effect=fake_sleep):
            _run(engine._wait_for_rate_limit("test"))

        self.assertEqual(len(slept), 1)
        # 5s 경과했으므로 sleep은 약 10s (±0.2s 허용)
        self.assertAlmostEqual(slept[0], engine._GEMINI_MIN_INTERVAL - 5.0, delta=0.2)

    def test_updates_last_call_start_after_gate(self):
        """게이트 통과 후 _last_call_start가 현재 시각으로 갱신된다."""
        import time as _t
        engine._last_call_start = _t.monotonic() - (engine._GEMINI_MIN_INTERVAL + 1.0)
        before = _t.monotonic()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            _run(engine._wait_for_rate_limit("test"))

        after = _t.monotonic()
        self.assertGreaterEqual(engine._last_call_start, before)
        self.assertLessEqual(engine._last_call_start, after + 0.1)

    def test_first_call_passes_immediately(self):
        """_last_call_start=0 (epoch) → elapsed 충분, 즉시 통과."""
        engine._last_call_start = 0.0  # epoch: 수십만 초 경과

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            _run(engine._wait_for_rate_limit("first"))
            mock_sleep.assert_not_called()


# ===========================================================================
# 4. _generate_with_retry — 429 처리
# ===========================================================================

class TestGenerateWithRetry429(unittest.TestCase):

    def setUp(self):
        engine._last_call_start = 0.0

    def _call(self, client):
        return _run(engine._generate_with_retry(
            client, config=_make_config(), contents="prompt", label="test"
        ))

    def test_429_then_success(self):
        """429 1회 후 성공 → 총 2회 호출."""
        success = MagicMock(text='{"ok": true}')
        client = _make_client(_Fake429(), success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.assertEqual(len(slept), 1)  # 429 대기 1회

    def test_429_uses_retry_info_delay(self):
        """RetryInfo.retryDelay 45s → max(45, 15) = 45s 대기."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake429(retry_delay=timedelta(seconds=45)), success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            self._call(client)

        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 45.0)

    def test_429_small_retry_info_uses_floor(self):
        """RetryInfo 5s < floor 15s → max(5, 15) = 15s 대기."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake429(retry_delay=5.0), success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            self._call(client)

        self.assertAlmostEqual(slept[0], engine._GEMINI_MIN_INTERVAL)

    def test_429_no_retry_info_uses_default(self):
        """RetryInfo 없음 → max(default=60, floor=15) = 60s 대기."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake429(), success)  # retry_delay=None

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            self._call(client)

        self.assertAlmostEqual(slept[0], engine._RETRY_429_DEFAULT_WAIT)

    def test_consecutive_429s_up_to_max_retries(self):
        """429가 max_retries번 → raise (총 max_retries+1회 호출)."""
        n = engine._RETRY_429_MAX_RETRIES + 1  # 4
        client = _make_client(*[_Fake429()] * n)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            with self.assertRaises(Exception):
                self._call(client)

        self.assertEqual(client.models.generate_content.call_count, n)
        self.assertEqual(len(slept), engine._RETRY_429_MAX_RETRIES)  # 3회 대기

    def test_429_within_max_retries_does_not_raise(self):
        """429가 max_retries번 이하이면 결국 성공."""
        success = MagicMock(text='{}')
        retries = engine._RETRY_429_MAX_RETRIES  # 3
        client = _make_client(*[_Fake429()] * retries, success)

        mock_sleep_ctx, _ = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        self.assertEqual(client.models.generate_content.call_count, retries + 1)


# ===========================================================================
# 5. _generate_with_retry — 503 처리
# ===========================================================================

class TestGenerateWithRetry503(unittest.TestCase):

    def setUp(self):
        engine._last_call_start = 0.0

    def _call(self, client):
        return _run(engine._generate_with_retry(
            client, config=_make_config(), contents="prompt", label="test-503"
        ))

    def test_503_then_success(self):
        """503 1회 후 성공 → 총 2회 호출, sleep 없음 (rate gate가 처리)."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake503(), success)

        gate_calls = []

        async def fake_gate(label=""):
            gate_calls.append(label)

        mock_sleep_ctx, slept = _patch_sleep()
        with patch("services.claude_engine._wait_for_rate_limit", side_effect=fake_gate), \
             mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        self.assertEqual(client.models.generate_content.call_count, 2)
        self.assertEqual(len(gate_calls), 2)  # 최초 + 503 재시도 각 1회
        self.assertEqual(len(slept), 0)       # sleep은 gate가 담당, 여기선 0

    def test_503_exhausted(self):
        """503이 max_attempts번 → raise."""
        n = engine._RETRY_MAX_ATTEMPTS  # 3
        client = _make_client(*[_Fake503()] * n)

        with _patch_rate_gate(), patch("asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(Exception):
                self._call(client)

        self.assertEqual(client.models.generate_content.call_count, n)

    def test_non_retryable_4xx_raises_immediately(self):
        """4xx(429 아님)는 즉시 raise — 재시도 없음."""
        exc = Exception("400 bad request")
        exc.code = 400
        exc.status_code = 400
        client = _make_client(exc)

        with _patch_rate_gate(), patch("asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(Exception):
                self._call(client)

        self.assertEqual(client.models.generate_content.call_count, 1)

    def test_rate_gate_called_before_every_503_retry(self):
        """503 재시도도 매번 rate gate를 통과한다."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake503(), _Fake503(), success)

        gate_calls = []

        async def fake_gate(label=""):
            gate_calls.append(label)

        with patch("services.claude_engine._wait_for_rate_limit", side_effect=fake_gate), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            self._call(client)

        self.assertEqual(len(gate_calls), 3)  # 최초 + 503×2 재시도


# ===========================================================================
# 6. _generate_with_retry — 503 후 429 혼합
# ===========================================================================

class TestGenerateWithRetry503Then429(unittest.TestCase):

    def setUp(self):
        engine._last_call_start = 0.0

    def _call(self, client):
        return _run(engine._generate_with_retry(
            client, config=_make_config(), contents="prompt", label="mixed"
        ))

    def test_503_then_429_then_success(self):
        """503 → 429 → 성공 시나리오."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake503(), _Fake429(), success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        self.assertEqual(client.models.generate_content.call_count, 3)
        # 429 대기 1회(60s default), 503 재시도는 sleep 없음
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], engine._RETRY_429_DEFAULT_WAIT)

    def test_429_then_503_then_success(self):
        """429 → 503 → 성공: 두 카운터가 독립적으로 동작한다."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake429(), _Fake503(), success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        self.assertEqual(client.models.generate_content.call_count, 3)
        self.assertEqual(len(slept), 1)  # 429 대기만

    def test_503_exhausted_before_reaching_429(self):
        """503이 max_attempts 도달 시 429에 도달하기 전에 raise."""
        n = engine._RETRY_MAX_ATTEMPTS
        client = _make_client(*[_Fake503()] * n)

        with _patch_rate_gate(), patch("asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(Exception):
                self._call(client)

        self.assertEqual(client.models.generate_content.call_count, n)

    def test_mixed_errors_eventually_succeed(self):
        """503×1, 429×1, 503×1 → 성공: 카운터가 독립적으로 허용 범위 내."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake503(), _Fake429(), _Fake503(), success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        self.assertEqual(client.models.generate_content.call_count, 4)
        self.assertEqual(len(slept), 1)  # 429 대기 1회

    def test_gate_called_for_every_attempt_in_mixed_scenario(self):
        """503·429·503 혼합 시 매 호출 전 rate gate 통과 확인."""
        success = MagicMock(text='{}')
        client = _make_client(_Fake503(), _Fake429(), success)

        gate_calls = []

        async def fake_gate(label=""):
            gate_calls.append(label)

        with patch("services.claude_engine._wait_for_rate_limit", side_effect=fake_gate), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            self._call(client)

        self.assertEqual(len(gate_calls), 3)


# ===========================================================================
# 7. 상수 값 검증
# ===========================================================================

class TestRateLimitConstants(unittest.TestCase):

    def test_min_interval_is_15(self):
        self.assertEqual(engine._GEMINI_MIN_INTERVAL, 15.0)

    def test_retry_max_attempts_is_3(self):
        self.assertEqual(engine._RETRY_MAX_ATTEMPTS, 3)

    def test_retry_429_max_retries_is_3(self):
        self.assertEqual(engine._RETRY_429_MAX_RETRIES, 3)

    def test_retry_429_default_wait_is_60(self):
        self.assertEqual(engine._RETRY_429_DEFAULT_WAIT, 60.0)

    def test_pipeline_soft_deadline_is_250(self):
        self.assertEqual(engine._PIPELINE_SOFT_DEADLINE_S, 250.0)

    def test_min_remaining_for_new_call_is_25(self):
        self.assertEqual(engine._MIN_REMAINING_FOR_NEW_CALL_S, 25.0)

    def test_last_call_start_exists(self):
        self.assertIsInstance(engine._last_call_start, float)

    def test_no_retry_base_delay(self):
        self.assertFalse(hasattr(engine, "_RETRY_BASE_DELAY"))

    def test_no_retry_jitter(self):
        self.assertFalse(hasattr(engine, "_RETRY_JITTER"))


# ===========================================================================
# 8. _generate_validated_package — max_retries=1 (이슈당 최대 2회 호출)
# ===========================================================================

class TestGenerateValidatedPackageMaxRetries(unittest.TestCase):
    """max_retries=1 기본값: 최초 1회 + 검증 재시도 1회 = 최대 2회 Gemini 호출."""

    def setUp(self):
        engine._last_call_start = 0.0
        engine._pipeline_start_time = 0.0

    def _good_package(self):
        return {
            "mid_topic": {
                "topic": "탐구질문 중급?",
                "reason": "이 주제는 학생들이 사회적 맥락에서 현상의 원인을 구조적으로 "
                          "분석하고 비판적 사고를 키우는 데 적합한 학문적 가치가 있다.",
                "grade_guide": {"grade1": "기초", "grade2": "심화", "grade3": "논증"},
                "level": "중",
            },
            "high_topic": {
                "topic": "탐구질문 고급?",
                "reason": "이 주제는 융합적 사고와 창의적 접근이 필요한 심화 탐구로 "
                          "기존 연구를 비판적으로 평가하고 독창적 가설을 제시할 수 있다.",
                "grade_guide": {"grade1": "관찰", "grade2": "비교", "grade3": "가설"},
                "level": "상",
            },
        }

    def _bad_package(self):
        """종결어미 없는 불완전 reason."""
        return {
            "mid_topic": {
                "topic": "탐구질문?",
                "reason": "이 주제는 학생들에게 중요한",  # 끊김
                "grade_guide": {"grade1": "기초", "grade2": "심화", "grade3": "논증"},
                "level": "중",
            },
            "high_topic": {
                "topic": "탐구질문?",
                "reason": "심화 학습에 적합하다.",
                "grade_guide": {"grade1": "관찰", "grade2": "비교", "grade3": "가설"},
                "level": "상",
            },
        }

    def test_first_attempt_success_uses_1_call(self):
        """최초 성공 → generate_exploration_package 1회 호출."""
        call_count = [0]

        async def mock_generate(issue):
            call_count[0] += 1
            return self._good_package()

        issue = {"title": "t", "track": "인문사회", "summary": "s", "keywords": []}
        with patch("services.claude_engine.generate_exploration_package",
                   side_effect=mock_generate):
            result = _run(engine._generate_validated_package(issue))

        self.assertEqual(call_count[0], 1)
        self.assertIn("mid_topic", result)

    def test_first_fail_retry_success_uses_2_calls(self):
        """첫 시도 검증 실패, 재시도 성공 → 2회 호출."""
        call_count = [0]

        async def mock_generate(issue):
            call_count[0] += 1
            return self._bad_package() if call_count[0] == 1 else self._good_package()

        issue = {"title": "t", "track": "인문사회", "summary": "s", "keywords": []}
        with patch("services.claude_engine.generate_exploration_package",
                   side_effect=mock_generate):
            result = _run(engine._generate_validated_package(issue))

        self.assertEqual(call_count[0], 2)
        self.assertIn("mid_topic", result)

    def test_both_attempts_fail_raises(self):
        """2회 모두 검증 실패 → ValueError (max_retries=1 → 총 2회 후 포기)."""
        call_count = [0]

        async def mock_generate(issue):
            call_count[0] += 1
            return self._bad_package()

        issue = {"title": "t", "track": "인문사회", "summary": "s", "keywords": []}
        with patch("services.claude_engine.generate_exploration_package",
                   side_effect=mock_generate):
            with self.assertRaises(ValueError):
                _run(engine._generate_validated_package(issue))

        # max_retries=1 → range(2) = [0, 1] = 총 2회 시도
        self.assertEqual(call_count[0], 2)

    def test_no_third_attempt_with_default_max_retries(self):
        """기본 max_retries=1이면 3회 이상 호출하지 않는다."""
        call_count = [0]

        async def mock_generate(issue):
            call_count[0] += 1
            return self._bad_package()

        issue = {"title": "t", "track": "인문사회", "summary": "s", "keywords": []}
        with patch("services.claude_engine.generate_exploration_package",
                   side_effect=mock_generate):
            with self.assertRaises(ValueError):
                _run(engine._generate_validated_package(issue))

        self.assertLessEqual(call_count[0], 2)


# ===========================================================================
# 9. 내부 마감시간 체크
# ===========================================================================

class TestRemainingBudget(unittest.TestCase):

    def setUp(self):
        engine._pipeline_start_time = 0.0

    def test_returns_inf_when_no_pipeline_started(self):
        engine._pipeline_start_time = 0.0
        self.assertEqual(engine._remaining_budget_s(), float("inf"))

    def test_returns_correct_remaining(self):
        import time as _time
        engine._pipeline_start_time = _time.monotonic() - 100.0
        remaining = engine._remaining_budget_s()
        # 250 - 100 = 150, 실제로는 약간 더 경과했을 수 있음
        self.assertAlmostEqual(remaining, 150.0, delta=1.0)

    def test_returns_negative_when_overdue(self):
        import time as _time
        engine._pipeline_start_time = _time.monotonic() - 260.0
        remaining = engine._remaining_budget_s()
        self.assertLess(remaining, 0)


class TestDeadlineInRunWeeklyGeneration(unittest.TestCase):
    """run_weekly_generation의 마감시간 체크 — 남은 시간이 부족하면 이슈를 건너뜀."""

    def setUp(self):
        engine._pipeline_start_time = 0.0
        engine._last_call_start = 0.0

    def _sample_news(self, n=10):
        return [
            {"title": f"뉴스 {i}", "summary": "요약", "url": f"https://x/{i}",
             "outlet": "test", "published_at": "2026-06-20T10:00:00+00:00"}
            for i in range(n)
        ]

    def _clustered(self, n=9):
        return [
            {"track": ["인문사회", "자연공학", "의약생명"][i % 3],
             "title": f"이슈 {i+1}", "summary": "s",
             "keywords": ["k1"], "sources": [{"outlet": "o", "url": "https://x"}]}
            for i in range(n)
        ]

    def _good_package(self):
        return {
            "mid_topic": {
                "topic": "탐구?",
                "reason": "이 주제는 사회 맥락에서 현상을 분석하고 비판적 사고력을 키울 수 있다.",
                "grade_guide": {"grade1": "기초", "grade2": "심화", "grade3": "논증"},
                "level": "중",
            },
            "high_topic": {
                "topic": "탐구고급?",
                "reason": "융합적 사고와 창의적 접근이 필요한 심화 탐구로 독창적 가설을 제시한다.",
                "grade_guide": {"grade1": "관찰", "grade2": "비교", "grade3": "가설"},
                "level": "상",
            },
        }

    def test_deadline_stops_remaining_issues(self):
        """마감시간 초과 시 처리 중단, 남은 이슈 실패 처리."""
        import time as _time
        news = self._sample_news()
        clustered = self._clustered(5)
        good_pkg = self._good_package()

        call_count = [0]

        async def mock_validate(issue):
            call_count[0] += 1
            # 2번째 이슈 처리 후 deadline 시뮬레이션
            if call_count[0] >= 2:
                # pipeline을 250s 이상 실행된 것처럼 설정
                engine._pipeline_start_time = _time.monotonic() - 249.0
            return good_pkg

        with patch("services.claude_engine.cluster_and_tag_issues",
                   new_callable=AsyncMock, return_value=clustered), \
             patch("services.claude_engine._generate_validated_package",
                   side_effect=mock_validate):
            result = _run(engine.run_weekly_generation(news))

        # 2개 성공 후 deadline 도달 → 3개 실패
        self.assertEqual(result.mode, "normal")
        self.assertEqual(result.generated_count, 2)
        self.assertEqual(result.failed_count, 3)
        self.assertEqual(result.attempted, 5)
        self.assertTrue(result.partial_success)

    def test_all_9_succeed_when_no_deadline_pressure(self):
        """시간 여유 충분 → 9개 모두 처리."""
        news = self._sample_news()
        clustered = self._clustered(9)
        good_pkg = self._good_package()

        # 파이프라인 방금 시작 (여유 250s)
        engine._pipeline_start_time = 0.0  # _remaining_budget_s() → inf

        with patch("services.claude_engine.cluster_and_tag_issues",
                   new_callable=AsyncMock, return_value=clustered), \
             patch("services.claude_engine._generate_validated_package",
                   new_callable=AsyncMock, return_value=good_pkg):
            result = _run(engine.run_weekly_generation(news))

        self.assertEqual(result.generated_count, 9)
        self.assertEqual(result.failed_count, 0)
        self.assertEqual(result.mode, "normal")


# ===========================================================================
# 10. 429 RetryInfo 예산 초과 처리
# ===========================================================================

class TestGenerateWithRetry429BudgetExceeded(unittest.TestCase):
    """429 대기 시간이 남은 예산을 초과하면 대기 없이 즉시 raise."""

    def setUp(self):
        engine._last_call_start = 0.0
        engine._pipeline_start_time = 0.0

    def _call(self, client):
        return _run(engine._generate_with_retry(
            client, config=_make_config(), contents="prompt", label="budget-test"
        ))

    def test_429_skipped_when_wait_exceeds_budget(self):
        """RetryInfo 45s + min_call 25s = 70s > remaining 30s → 즉시 raise."""
        import time as _time
        # 남은 예산 30s 시뮬레이션: pipeline 220s 경과
        engine._pipeline_start_time = _time.monotonic() - 220.0

        exc_429 = _Fake429(retry_delay=45.0)
        client = _make_client(exc_429)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            with self.assertRaises(Exception):
                self._call(client)

        # 429 대기 sleep이 호출되지 않아야 함
        self.assertEqual(len(slept), 0)
        self.assertEqual(client.models.generate_content.call_count, 1)

    def test_429_waits_when_budget_sufficient(self):
        """대기 후에도 예산이 남으면 정상적으로 대기하고 재시도."""
        import time as _time
        # 남은 예산 200s: wait 60s + 25s = 85s < 200s → 대기 허용
        engine._pipeline_start_time = _time.monotonic() - 50.0

        exc_429 = _Fake429()  # retry_delay=None → default 60s wait
        success = MagicMock(text='{}')
        client = _make_client(exc_429, success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], engine._RETRY_429_DEFAULT_WAIT)

    def test_no_budget_limit_outside_pipeline(self):
        """_pipeline_start_time=0 (파이프라인 외부) → 예산 무제한, 정상 대기."""
        engine._pipeline_start_time = 0.0  # inf budget

        exc_429 = _Fake429(retry_delay=120.0)  # 큰 RetryInfo
        success = MagicMock(text='{}')
        client = _make_client(exc_429, success)

        mock_sleep_ctx, slept = _patch_sleep()
        with _patch_rate_gate(), mock_sleep_ctx:
            result = self._call(client)

        self.assertEqual(result, success)
        # max(120s, 15s) = 120s 대기
        self.assertAlmostEqual(slept[0], 120.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
