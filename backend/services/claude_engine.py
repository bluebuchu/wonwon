import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import (
    settings,
    GEMINI_MODEL,
    TOTAL_ISSUES,
    ISSUES_PER_TRACK,
    MIN_ISSUES_TOTAL,
    RAW_FALLBACK_COUNT,
)


@dataclass
class WeeklyGenerationResult:
    """
    run_weekly_generation의 반환.

    mode:
      - "normal": AI 정상 경로로 1개 이상 생성됨 (부분 성공 포함)
      - "raw_fallback": AI 단계 전수 실패로 RSS 원문 N개로 강등 발행
    """
    packages: List["IssuePackage"]
    mode: str
    generated_count: int        # AI로 생성된 패키지 수
    failed_count: int           # AI에서 실패한 이슈 수
    raw_fallback_count: int     # raw fallback으로 채운 카드 수
    attempted: int              # 클러스터링이 산출한 이슈 후보 수 (raw mode에선 0)
    failed_titles: List[str]    # AI 실패 이슈 제목 (raw mode에선 [])
    reason: str | None = None   # "clustering_failed" | "all_issues_failed" | None

    @property
    def partial_success(self) -> bool:
        """AI 정상 경로에서 일부만 성공한 경우만 True. raw_fallback은 False."""
        return self.mode == "normal" and self.failed_count > 0
from models import (
    ExplorationTopic,
    GradeGuide,
    IssuePackage,
    NewsSource,
    TrackType,
)

logger = logging.getLogger(__name__)


def _get_client():
    return genai.Client(api_key=settings.google_api_key)


def _remaining_budget_s() -> float:
    """파이프라인 시작 기준 남은 처리 시간(초)을 반환한다.
    _pipeline_start_time이 0이면 (파이프라인 외부 단독 호출) 무제한(inf)으로 취급한다."""
    if _pipeline_start_time == 0.0:
        return float("inf")
    return _PIPELINE_SOFT_DEADLINE_S - (time.monotonic() - _pipeline_start_time)


# --- 호출 간격 · 재시도 상수 ---------------------------------------------------
# 아래 값을 조정해 호출 정책을 바꿀 수 있다.

_GEMINI_MIN_INTERVAL: float = 15.0
"""모든 Gemini API 호출 간 최소 간격(초).
5 RPM 무료 티어 기준 최소 12s 필요 + 3s 안전 버퍼."""

_RETRY_MAX_ATTEMPTS: int = 3
"""503/5xx 서버 오류 시 총 시도 횟수 (최초 1회 포함, 재시도 최대 2회)."""

_RETRY_429_MAX_RETRIES: int = 3
"""429 요청 한도 초과 시 최대 재시도 횟수 (첫 429 이후 최대 3번 더 시도)."""

_RETRY_429_DEFAULT_WAIT: float = 60.0
"""429 응답에 RetryInfo.retryDelay가 없을 때 적용할 기본 대기 시간(초)."""

_last_call_start: float = 0.0
"""마지막 Gemini API 호출을 시작한 시각 (time.monotonic() 기준).
_wait_for_rate_limit()가 갱신한다."""

_PIPELINE_SOFT_DEADLINE_S: float = 250.0
"""파이프라인 내부 처리 마감시간(초). Vercel maxDuration(300s)에서 50s 마진을 뺀 값.
이 시간이 경과하면 새로운 Gemini 호출을 시작하지 않는다."""

_MIN_REMAINING_FOR_NEW_CALL_S: float = 25.0
"""새 Gemini 호출을 시작하기 위해 남아 있어야 하는 최소 여유 시간(초).
rate gate 15s + API 응답 예상 시간 ~10s."""

_pipeline_start_time: float = 0.0
"""run_weekly_generation 시작 시각 (time.monotonic() 기준).
_remaining_budget_s()가 이 값을 참조한다."""


def _exc_diag(exc: Exception) -> str:
    """예외의 타입/code/status 등을 한 줄로 요약. SDK 버전 차이로 판정 실패 시 진단용."""
    return (
        f"type={type(exc).__module__}.{type(exc).__name__} "
        f"code={getattr(exc, 'code', None)!r} "
        f"status_code={getattr(exc, 'status_code', None)!r} "
        f"status={getattr(exc, 'status', None)!r} "
        f"msg={str(exc)[:300]}"
    )


def _is_retryable_server_error(exc: Exception) -> bool:
    """
    5xx 일시 오류만 retry 대상으로 한다. google-genai 버전/래핑 차이를 흡수하기 위해
    다중 경로로 판정: ServerError → APIError → code/status_code 속성 → status 문자열 → 메시지.
    """
    # 1. google-genai 표준 ServerError
    if isinstance(exc, genai_errors.ServerError):
        return True
    # 2. APIError(상위)인데 code가 5xx인 경우 (일부 버전은 ServerError 미사용)
    if isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", None)
        if isinstance(code, int) and 500 <= code < 600:
            return True
    # 3. 일반 속성 검사 — httpx 계열이나 래핑된 예외 대응
    for attr in ("code", "status_code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int) and 500 <= val < 600:
            return True
    # 4. Gemini status 문자열 (UNAVAILABLE=503, INTERNAL=500, DEADLINE_EXCEEDED=504)
    status = getattr(exc, "status", None)
    if isinstance(status, str) and status.upper() in {
        "UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED",
    }:
        return True
    # 5. 마지막 보루: 메시지 패턴 매칭
    msg = str(exc).lower()
    if any(tok in msg for tok in ("503", "500", "unavailable", "overloaded", "internal error")):
        return True
    return False


async def _wait_for_rate_limit(label: str = "") -> None:
    """
    모든 Gemini API 호출 직전에 반드시 호출하는 전역 속도 제한 게이트.

    _last_call_start 기준으로 _GEMINI_MIN_INTERVAL(15s)이 경과하지 않았으면
    부족분을 대기한 뒤 _last_call_start를 현재 시각으로 갱신한다.

    클러스터링, 이슈 생성, 503 재시도, 429 재시도 모두 이 게이트를 통과한다.
    실제 요청 시작 시각 기준으로 간격을 계산하므로 API 응답 시간은 간격에 포함되지 않는다.
    """
    global _last_call_start
    now = time.monotonic()
    elapsed = now - _last_call_start
    if elapsed < _GEMINI_MIN_INTERVAL:
        gap = _GEMINI_MIN_INTERVAL - elapsed
        logger.info(
            f"[rate-gate] '{label}' elapsed={elapsed:.1f}s < {_GEMINI_MIN_INTERVAL}s — "
            f"sleeping {gap:.2f}s"
        )
        await asyncio.sleep(gap)
    _last_call_start = time.monotonic()


def _is_rate_limit_error(exc: Exception) -> bool:
    """
    429 RESOURCE_EXHAUSTED(요청 한도 초과) 여부를 판정한다.
    SDK 버전·래핑 차이를 흡수하기 위해 다중 경로로 판정한다.
    """
    if isinstance(exc, genai_errors.ClientError):
        if getattr(exc, "code", None) == 429:
            return True
    for attr in ("code", "status_code"):
        if getattr(exc, attr, None) == 429:
            return True
    status = getattr(exc, "status", None)
    if isinstance(status, str) and status.upper() == "RESOURCE_EXHAUSTED":
        return True
    msg = str(exc).lower()
    return any(tok in msg for tok in ("429", "resource exhausted", "quota exceeded", "rate limit"))


def _extract_429_retry_delay(exc: Exception) -> float | None:
    """
    429 응답의 RetryInfo.retryDelay를 읽어 초 단위로 반환한다. 파싱 불가 시 None 반환.

    시도 순서:
    1. SDK retry_delay 속성 (datetime.timedelta 또는 숫자)
    2. error.details 리스트의 gRPC RetryInfo 구조체
    3. 에러 메시지의 "retry after Ns" 패턴
    """
    raw = getattr(exc, "retry_delay", None)
    if raw is not None:
        if hasattr(raw, "total_seconds"):
            return float(raw.total_seconds())
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    for detail in getattr(exc, "details", []) or []:
        rd = getattr(detail, "retry_delay", None)
        if rd is not None:
            seconds = getattr(rd, "seconds", 0) or 0
            nanos = getattr(rd, "nanos", 0) or 0
            return float(seconds + nanos / 1e9)
    m = re.search(r"retry[_ ]?after[:\s]+(\d+(?:\.\d+)?)\s*s", str(exc).lower())
    if m:
        return float(m.group(1))
    return None


async def _generate_with_retry(
    client: Any,
    *,
    config: types.GenerateContentConfig,
    contents: str,
    label: str,
) -> Any:
    """
    Gemini generate_content 호출에 전역 호출 간격 제어 + 재시도 정책 적용.

    모든 호출(최초·503 재시도·429 재시도) 전 _wait_for_rate_limit()를 통해
    _GEMINI_MIN_INTERVAL(15s) 간격을 보장한다.

    - 429: RetryInfo.retryDelay와 _GEMINI_MIN_INTERVAL 중 max를 대기.
           최대 _RETRY_429_MAX_RETRIES회 재시도 후 초과 시 raise.
    - 503/5xx: rate gate 통과 후 재시도. 총 _RETRY_MAX_ATTEMPTS회 시도 후 raise.
    - 기타 4xx / 파싱 오류: 즉시 raise.
    """
    server_errors = 0   # 5xx 오류 누적 횟수 (첫 시도 포함)
    rate_errors = 0     # 429 누적 횟수

    while True:
        # ── 전역 호출 간격 게이트 (클러스터링·이슈·503·429 재시도 모두 통과) ──
        await _wait_for_rate_limit(label)

        try:
            return client.models.generate_content(
                model=GEMINI_MODEL,
                config=config,
                contents=contents,
            )
        except Exception as e:
            diag = _exc_diag(e)

            # ── 429 RESOURCE_EXHAUSTED ────────────────────────────────────────
            if _is_rate_limit_error(e):
                rate_errors += 1
                logger.warning(
                    f"[gemini-retry] '{label}' 429 rate limit "
                    f"(occurrence {rate_errors}/{_RETRY_429_MAX_RETRIES}) — {diag}"
                )
                if rate_errors > _RETRY_429_MAX_RETRIES:
                    logger.error(
                        f"[gemini-retry] '{label}' 429 exhausted after "
                        f"{rate_errors} occurrences — raising"
                    )
                    raise
                raw_delay = _extract_429_retry_delay(e)
                wait = max(
                    raw_delay if raw_delay is not None else _RETRY_429_DEFAULT_WAIT,
                    _GEMINI_MIN_INTERVAL,
                )
                # 예산 초과 확인: 대기 후 재시도할 시간이 남지 않으면 이슈 실패 처리
                remaining = _remaining_budget_s()
                if wait + _MIN_REMAINING_FOR_NEW_CALL_S > remaining:
                    logger.warning(
                        f"[gemini-retry] '{label}' 429 wait {wait:.0f}s + "
                        f"min_call {_MIN_REMAINING_FOR_NEW_CALL_S:.0f}s "
                        f"> remaining {remaining:.0f}s — "
                        f"skipping retry to stay within deadline"
                    )
                    raise
                logger.warning(
                    f"[gemini-retry] '{label}' 429 waiting {wait:.1f}s "
                    f"(RetryInfo={raw_delay}s, floor={_GEMINI_MIN_INTERVAL}s, "
                    f"remaining={remaining:.0f}s)"
                )
                await asyncio.sleep(wait)
                # 429 대기는 min_interval 이상이므로 다음 루프의 rate gate는 즉시 통과.
                continue

            # ── 503/5xx 서버 오류 ─────────────────────────────────────────────
            retryable = _is_retryable_server_error(e)
            server_errors += 1
            logger.warning(
                f"[gemini-retry] '{label}' server error attempt "
                f"{server_errors}/{_RETRY_MAX_ATTEMPTS} (retryable={retryable}) — {diag}"
            )
            if not retryable:
                raise
            if server_errors >= _RETRY_MAX_ATTEMPTS:
                logger.error(
                    f"[gemini-retry] '{label}' 503 exhausted after "
                    f"{server_errors}/{_RETRY_MAX_ATTEMPTS} attempts — raising"
                )
                raise
            # 다음 루프의 _wait_for_rate_limit()가 15s 간격을 보장.
            # 이전의 짧은 exponential backoff(1s, 2s)는 rate gate로 대체됨.


_SENTENCE_TERMINATORS = (".", "?", "!", "。", "？", "！", "”", "’", "」", "』", "…")


def _is_complete_sentence(text: str) -> bool:
    """reason 문자열이 종결어미/마침표로 끝나는지 검증. 중간에서 끊긴 응답 식별용."""
    if not text:
        return False
    stripped = text.rstrip()
    return bool(stripped) and stripped.endswith(_SENTENCE_TERMINATORS)


def _get_current_week_date() -> str:
    """Return this week's Friday date as YYYY-MM-DD."""
    today = datetime.now(timezone.utc)
    days_since_friday = (today.weekday() - 4) % 7
    friday = today - timedelta(days=days_since_friday)
    return friday.strftime("%Y-%m-%d")


CLUSTERING_SYSTEM_PROMPT = """당신은 국내 고등학생 탐구활동 설계를 돕는 계열별 탐구 큐레이터다.

당신의 역할은 최신 뉴스 기사들을 분석하여 고등학생의 탐구 활동에 적합한 이슈를 선별하고 구조화하는 것이다.

다음 기준에 따라 이슈를 선별한다:
- 포함: 정책, 기술, 교육, 환경, 생명과학, AI/인공지능, 사회적 불평등, 의료, 과학, 경제, 국제 관계
- 제외: 연예, 스포츠, 단순 사건/사고, 오락

계열은 세 가지로 구분한다:
- 인문사회: 사회, 역사, 문화, 경제, 정치, 법, 교육, 윤리 관련 이슈
- 자연공학: 물리, 화학, 수학, 공학, 기술, 환경, 기후 관련 이슈
- 의약생명: 의학, 생명과학, 바이오, 보건, 뇌과학, 유전공학 관련 이슈"""


GENERATION_SYSTEM_PROMPT = """당신은 국내 고등학생 탐구활동 설계를 돕는 계열별 탐구 큐레이터다.

## 탐구 주제 생성 원칙 (반드시 준수)

1. **질문 형식 필수**: 모든 탐구 주제는 반드시 "~인가?", "~할 수 있는가?", "~에 어떤 영향을 미치는가?" 등 질문 형식으로 작성한다.

2. **구조적 탐구 (표면적 접근 금지)**: 단순히 "~를 조사하시오"가 아닌, 현상의 원인, 메커니즘, 사회적 영향, 해결방안을 탐구하는 주제를 생성한다.

3. **계열 연계성**: 해당 계열(인문사회/자연공학/의약생명)의 학문적 방법론과 개념을 활용할 수 있는 주제를 선정한다.

4. **시의성**: 현재 사회 이슈와 연결되어 학생이 실제 의미를 느낄 수 있는 주제여야 한다.

5. **학년별 차별화**:
   - 1학년: 기초 개념 탐구, 현상 파악 중심, 문헌 조사 수준
   - 2학년: 심화 분석, 비교 연구, 데이터 수집/분석 포함
   - 3학년: 독창적 가설 설정, 비판적 평가, 학문적 논증 수준

6. **난이도 구분**:
   - [중] 수준: 교과 지식 활용, 명확한 탐구 방향, 일반 고등학생 수행 가능
   - [상] 수준: 융합적 사고, 창의적 접근, 심화 탐구 역량 필요

7. **선택 이유 작성 기준** (150-350자):
   - 해당 이슈가 탐구 주제로 적합한 학문적 이유를 설명한다
   - 학생이 이 주제를 통해 무엇을 배울 수 있는지 명시한다
   - 사회적 맥락과 학문적 연결점을 제시한다

8. **학년별 가이드 작성 기준**:
   - 각 학년에서 수행할 수 있는 구체적인 탐구 방법을 1-2문장으로 안내한다
   - 활용 가능한 자료, 방법론, 접근법을 포함한다"""


async def cluster_and_tag_issues(news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Send news items to Claude to cluster them into 9 issues (3 per track).
    Returns structured list of issue dicts.
    """
    client = _get_client()

    # Prepare news items text (limit to top 60 items to avoid token limits)
    news_text = ""
    for i, item in enumerate(news_items[:60], 1):
        news_text += f"""
[기사 {i}]
제목: {item['title']}
언론사: {item['outlet']}
요약: {item.get('summary', '')[:200]}
URL: {item.get('url', '')}
"""

    prompt = f"""다음은 이번 주 수집된 국내 뉴스 기사 목록이다.

{news_text}

## 지시사항

위 뉴스 기사들을 분석하여 고등학생 탐구 활동에 적합한 9개의 이슈를 선별하고 구조화하라.

구성:
- 인문사회 계열: 3개 이슈
- 자연공학 계열: 3개 이슈
- 의약생명 계열: 3개 이슈

각 이슈에 대해 다음 JSON 형식으로 반환하라:

```json
{{
  "issues": [
    {{
      "track": "인문사회",
      "title": "이슈 제목 (간결하고 명확하게)",
      "summary": "이슈에 대한 구조적 요약 (2-4문장, 현상-원인-의미 구조)",
      "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
      "sources": [
        {{"outlet": "언론사명", "url": "기사URL"}},
        {{"outlet": "언론사명", "url": "기사URL"}}
      ]
    }}
  ]
}}
```

요구사항:
1. 각 계열별로 정확히 3개씩 총 9개 이슈를 선별한다
2. 연예, 스포츠, 단순 사건/사고는 제외한다
3. 정책, 기술, 교육, 환경, 의료, 과학, AI 등 탐구 가치 있는 이슈를 우선 선택한다
4. 각 이슈의 summary는 단순 사실 나열이 아닌 현상의 구조적 설명이어야 한다
5. keywords는 고등학생이 탐구에서 활용할 핵심 개념어 5개를 선정한다
6. sources는 해당 이슈와 직접 관련된 기사 URL을 2-5개 포함한다
7. 반드시 유효한 JSON만 반환하고, JSON 외 다른 텍스트는 포함하지 않는다"""

    try:
        response = await _generate_with_retry(
            client,
            config=types.GenerateContentConfig(system_instruction=CLUSTERING_SYSTEM_PROMPT),
            contents=prompt,
            label="cluster_and_tag_issues",
        )
        response_text = response.text.strip()

        # Extract JSON from response
        if "```json" in response_text:
            start = response_text.index("```json") + 7
            end = response_text.index("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.index("```") + 3
            end = response_text.index("```", start)
            response_text = response_text[start:end].strip()

        data = json.loads(response_text)
        issues = data.get("issues", [])

        logger.info(f"Gemini clustered {len(issues)} issues from {len(news_items)} news items")
        return issues

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini clustering response as JSON: {e}")
        raise ValueError(f"Gemini returned invalid JSON: {e}")
    except Exception as e:
        logger.error(f"Error in cluster_and_tag_issues: {e}")
        raise


async def generate_exploration_package(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    For one issue, generate [중] and [상] exploration topics with grade guides.
    Returns {mid_topic: ExplorationTopic, high_topic: ExplorationTopic}
    """
    client = _get_client()

    track = issue.get("track", "")
    title = issue.get("title", "")
    summary = issue.get("summary", "")
    keywords = ", ".join(issue.get("keywords", []))

    prompt = f"""다음 이슈에 대한 고등학생 탐구 주제 패키지를 생성하라.

## 이슈 정보
- 계열: {track}
- 제목: {title}
- 요약: {summary}
- 핵심 키워드: {keywords}

## 생성 요구사항

[중] 수준과 [상] 수준 탐구 주제를 각각 1개씩 생성하라.
각 탐구 주제는 반드시 질문 형식이어야 한다.

다음 JSON 형식으로 반환하라:

```json
{{
  "mid_topic": {{
    "topic": "탐구 주제 질문 (중급)",
    "reason": "탐구 선택 이유 (150-350자, 학문적 근거와 학습 가치 포함)",
    "grade_guide": {{
      "grade1": "1학년 탐구 방향 및 구체적 활동 방법 (1-2문장)",
      "grade2": "2학년 탐구 방향 및 심화 활동 방법 (1-2문장)",
      "grade3": "3학년 탐구 방향 및 고급 활동 방법 (1-2문장)"
    }},
    "level": "중"
  }},
  "high_topic": {{
    "topic": "탐구 주제 질문 (고급)",
    "reason": "탐구 선택 이유 (150-350자, 융합적 접근과 심화 학습 가치 포함)",
    "grade_guide": {{
      "grade1": "1학년 기초 탐구 방향 (1-2문장)",
      "grade2": "2학년 심화 탐구 방향 (1-2문장)",
      "grade3": "3학년 고급 탐구 방향 (1-2문장)"
    }},
    "level": "상"
  }}
}}
```

추가 요구사항:
1. [중] 주제: {track} 계열 교과 지식으로 탐구 가능하고, 명확한 탐구 방향이 있어야 함
2. [상] 주제: 융합적 사고와 창의적 접근이 필요하며, 기존 연구를 비판적으로 평가하는 수준
3. reason 필드는 반드시 150자 이상 350자 이하로 작성
4. 각 grade_guide는 해당 학년 수준에 적합한 구체적 탐구 방법 제시
5. 반드시 유효한 JSON만 반환하고, JSON 외 다른 텍스트는 포함하지 않는다"""

    try:
        response = await _generate_with_retry(
            client,
            config=types.GenerateContentConfig(system_instruction=GENERATION_SYSTEM_PROMPT),
            contents=prompt,
            label=f"generate_exploration_package:{title}",
        )
        response_text = response.text.strip()

        # Extract JSON from response
        if "```json" in response_text:
            start = response_text.index("```json") + 7
            end = response_text.index("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.index("```") + 3
            end = response_text.index("```", start)
            response_text = response_text[start:end].strip()

        data = json.loads(response_text)
        logger.info(f"Generated exploration package for issue: {title}")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini package response as JSON: {e}")
        raise ValueError(f"Gemini returned invalid JSON for package: {e}")
    except Exception as e:
        logger.error(f"Error generating exploration package for '{title}': {e}")
        raise


def _build_issue_package(
    issue_dict: Dict[str, Any],
    package: Dict[str, Any],
    week_date: str,
) -> IssuePackage:
    """Convert raw dicts into a validated IssuePackage model."""
    track_map = {
        "인문사회": TrackType.humanities_social,
        "자연공학": TrackType.natural_engineering,
        "의약생명": TrackType.medical_life,
    }

    track = track_map.get(issue_dict.get("track", ""), TrackType.humanities_social)

    sources = [
        NewsSource(outlet=s.get("outlet", ""), url=s.get("url", ""))
        for s in issue_dict.get("sources", [])
    ]

    def build_topic(raw: Dict[str, Any], level: str) -> ExplorationTopic:
        grade_raw = raw.get("grade_guide", {})
        grade_guide = GradeGuide(
            grade1=grade_raw.get("grade1", ""),
            grade2=grade_raw.get("grade2", ""),
            grade3=grade_raw.get("grade3", ""),
        )
        reason = raw.get("reason", "")
        # 너무 짧을 때만 안전 패딩. 상한 슬라이스는 종결어미를 잘라내므로 제거
        # — 길이 검증은 Pydantic max_length=500이, 종결 검증은 _is_complete_sentence가 담당
        if len(reason) < 150:
            reason = reason + " 이 탐구 주제는 학생들이 현재 사회 문제를 학문적으로 분석하고 비판적 사고력을 키우는 데 도움이 된다."

        return ExplorationTopic(
            topic=raw.get("topic", ""),
            reason=reason,
            grade_guide=grade_guide,
            level=level,
        )

    mid_raw = package.get("mid_topic", {})
    high_raw = package.get("high_topic", {})

    return IssuePackage(
        id=str(uuid.uuid4()),
        week_date=week_date,
        title=issue_dict.get("title", ""),
        track=track,
        summary=issue_dict.get("summary", ""),
        keywords=issue_dict.get("keywords", []),
        sources=sources,
        mid_topic=build_topic(mid_raw, "중"),
        high_topic=build_topic(high_raw, "상"),
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Raw fallback — AI 호출 없이 RSS 원문만으로 IssuePackage를 만든다.
# Gemini가 다운된 상황에서도 주간 발행을 유지하기 위한 강등 경로.
# ---------------------------------------------------------------------------

_TRACK_CYCLE: List[TrackType] = [
    TrackType.humanities_social,
    TrackType.natural_engineering,
    TrackType.medical_life,
]

_RAW_PLACEHOLDER_TOPIC = (
    "이번 주는 AI 분석 서비스 장애로 원문 뉴스 기반 탐구 카드가 제공됩니다."
)
# ExplorationTopic.reason 은 min_length=30 (완화됨). placeholder를 짧게 유지.
_RAW_PLACEHOLDER_REASON = (
    "이번 주는 AI 분석 서비스 장애로 원문 뉴스 기반 탐구 카드가 제공됩니다. "
    "원문 기사 링크를 참고하세요. 다음 정기 발행에서 자동 복구됩니다."
)
_RAW_PLACEHOLDER_GRADE = "—"


def _build_raw_fallback_packages(
    news_items: List[Dict[str, Any]],
    week_date: str,
    n: int = RAW_FALLBACK_COUNT,
) -> List[IssuePackage]:
    """
    Gemini 호출 없이 RSS 원문 헤드라인만으로 IssuePackage n개를 만든다.

    - published_at 내림차순 상위 n개 선택 (None은 가장 오래된 것으로 취급)
    - 트랙은 round-robin (TRACK_CYCLE[i % 3])
    - exploration topics는 placeholder. 사용자에게 raw fallback 모드임을 명시.
    """
    if not news_items:
        return []

    sorted_items = sorted(
        news_items,
        key=lambda x: x.get("published_at") or "",
        reverse=True,
    )[:n]

    grade_guide = GradeGuide(
        grade1=_RAW_PLACEHOLDER_GRADE,
        grade2=_RAW_PLACEHOLDER_GRADE,
        grade3=_RAW_PLACEHOLDER_GRADE,
    )

    packages: List[IssuePackage] = []
    for i, item in enumerate(sorted_items):
        title = (item.get("title") or "").strip() or "(제목 없음)"
        summary_text = (item.get("summary") or "").strip() or "원본 기사 링크를 참고하세요."
        track = _TRACK_CYCLE[i % 3]
        sources = [NewsSource(
            outlet=item.get("outlet", ""),
            url=item.get("url", ""),
        )]
        mid_topic = ExplorationTopic(
            topic=_RAW_PLACEHOLDER_TOPIC,
            reason=_RAW_PLACEHOLDER_REASON,
            grade_guide=grade_guide,
            level="중",
        )
        high_topic = ExplorationTopic(
            topic=_RAW_PLACEHOLDER_TOPIC,
            reason=_RAW_PLACEHOLDER_REASON,
            grade_guide=grade_guide,
            level="상",
        )
        packages.append(IssuePackage(
            id=str(uuid.uuid4()),
            week_date=week_date,
            title=title[:300],
            track=track,
            summary=summary_text[:500],
            keywords=[],
            sources=sources,
            mid_topic=mid_topic,
            high_topic=high_topic,
            created_at=datetime.now(timezone.utc),
        ))
    return packages


def _make_raw_fallback_result(
    news_items: List[Dict[str, Any]],
    week_date: str,
    *,
    reason: str,
    attempted: int = 0,
    failed_titles: List[str] | None = None,
) -> WeeklyGenerationResult:
    raw_packages = _build_raw_fallback_packages(news_items, week_date)
    logger.warning(
        f"[raw-fallback] reason={reason} count={len(raw_packages)} "
        f"attempted={attempted} failed_titles={failed_titles or []}"
    )
    return WeeklyGenerationResult(
        packages=raw_packages,
        mode="raw_fallback",
        generated_count=0,
        failed_count=attempted,  # attempted된 만큼은 실패로 카운트
        raw_fallback_count=len(raw_packages),
        attempted=attempted,
        failed_titles=failed_titles or [],
        reason=reason,
    )


async def _generate_validated_package(
    issue: Dict[str, Any],
    max_retries: int = 1,
) -> Dict[str, Any]:
    """
    generate_exploration_package를 호출하되 mid/high reason이 종결어미로 끝나는지 검증.
    중간 절단된 응답이면 최대 max_retries회 재생성(기본 1회 → 이슈당 최대 2회 Gemini 호출).
    모두 실패하면 ValueError 발생 → 호출부(run_weekly_generation)가 건너뛴다.
    """
    title = issue.get("title", "")
    last_error: str = ""
    for attempt in range(max_retries + 1):
        package = await generate_exploration_package(issue)
        mid_reason = (package.get("mid_topic") or {}).get("reason", "")
        high_reason = (package.get("high_topic") or {}).get("reason", "")
        if _is_complete_sentence(mid_reason) and _is_complete_sentence(high_reason):
            return package
        last_error = (
            f"incomplete reason — mid_tail='{mid_reason[-20:]}' "
            f"high_tail='{high_reason[-20:]}'"
        )
        logger.warning(
            f"[validation] '{title}' attempt {attempt+1}/{max_retries+1}: {last_error}"
        )
    raise ValueError(
        f"reason validation failed after {max_retries+1} attempts: {last_error}"
    )


async def run_weekly_generation(
    news_items: List[Dict[str, Any]],
) -> WeeklyGenerationResult:
    """
    주간 생성 파이프라인.

    1. clustering (Gemini)
       - 실패 시 raw fallback 발행 (reason="clustering_failed")
       - 빈 결과 시 raw fallback 발행 (reason="clustering_empty")
    2. per-issue 생성 (Gemini) — 개별 실패는 continue
       - 각 이슈 전 내부 마감시간 체크 (_PIPELINE_SOFT_DEADLINE_S=250s)
       - 0건 성공 시 raw fallback 발행 (reason="all_issues_failed")
    3. 1건 이상 성공 시 normal mode 결과 반환 (partial 포함)

    정책:
    - 어떤 AI 실패도 호출부로 raise 하지 않는다.
    - news_items 자체가 비어있는 경우는 호출 전에 cron.py가 거른다 (이 함수에서는 raw 0건).
    """
    global _pipeline_start_time
    _pipeline_start_time = time.monotonic()

    week_date = _get_current_week_date()

    logger.info(f"Starting weekly generation for week: {week_date}")
    logger.info(f"Input news items: {len(news_items)}")
    logger.info(
        f"[deadline] soft_deadline={_PIPELINE_SOFT_DEADLINE_S}s "
        f"min_per_call={_MIN_REMAINING_FOR_NEW_CALL_S}s"
    )

    failed_titles: List[str] = []

    # --- Step 1: Cluster ---
    try:
        issue_dicts = await cluster_and_tag_issues(news_items)
    except Exception as e:
        logger.error(f"[clustering] exhausted retries: {e}", exc_info=True)
        return _make_raw_fallback_result(
            news_items, week_date, reason="clustering_failed",
        )

    if not issue_dicts:
        logger.warning("[clustering] returned empty issue list")
        return _make_raw_fallback_result(
            news_items, week_date, reason="clustering_empty",
        )

    attempted = len(issue_dicts)
    logger.info(f"Clustered into {attempted} issues")

    # --- Step 2: Per-issue generation (partial-success policy) ---
    issue_packages: List[IssuePackage] = []
    for i, issue_dict in enumerate(issue_dicts):
        title = issue_dict.get("title", f"issue_{i+1}")

        # ── 내부 마감시간 체크: 여유가 없으면 남은 이슈를 모두 실패 처리 ──────
        remaining = _remaining_budget_s()
        if remaining < _MIN_REMAINING_FOR_NEW_CALL_S:
            skipped = [
                d.get("title", f"issue_{j+1}")
                for j, d in enumerate(issue_dicts[i:], i)
            ]
            logger.warning(
                f"[deadline] {remaining:.0f}s remaining < "
                f"{_MIN_REMAINING_FOR_NEW_CALL_S}s — "
                f"stopping at issue {i+1}/{attempted}. "
                f"Skipping: {skipped}"
            )
            failed_titles.extend(skipped)
            break

        try:
            logger.info(
                f"Generating package {i+1}/{attempted}: {title} "
                f"(remaining={remaining:.0f}s)"
            )
            package = await _generate_validated_package(issue_dict)
            issue_package = _build_issue_package(issue_dict, package, week_date)
            issue_packages.append(issue_package)
        except Exception as e:
            logger.error(f"Failed to generate package for '{title}': {e}")
            failed_titles.append(title)
            continue

    generated = len(issue_packages)
    failed = attempted - generated

    # --- Step 3: 전수 실패도 raw fallback으로 강등 ---
    if generated < MIN_ISSUES_TOTAL:
        logger.warning(
            f"[generation] 0 succeeded out of {attempted}; raw fallback 강등. "
            f"failed_titles={failed_titles}"
        )
        return _make_raw_fallback_result(
            news_items, week_date,
            reason="all_issues_failed",
            attempted=attempted,
            failed_titles=failed_titles,
        )

    track_counts: Dict[str, int] = {}
    for pkg in issue_packages:
        track_counts[pkg.track.value] = track_counts.get(pkg.track.value, 0) + 1
    partial = failed > 0
    logger.info(
        f"Weekly generation complete: mode=normal partial_success={partial} "
        f"generated={generated} failed={failed} attempted={attempted} "
        f"per_track={track_counts} failed_titles={failed_titles}"
    )
    return WeeklyGenerationResult(
        packages=issue_packages,
        mode="normal",
        generated_count=generated,
        failed_count=failed,
        raw_fallback_count=0,
        attempted=attempted,
        failed_titles=failed_titles,
        reason=None,
    )
