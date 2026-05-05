import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from config import settings, GEMINI_MODEL, TOTAL_ISSUES, ISSUES_PER_TRACK
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


_RETRY_MAX_ATTEMPTS = 4
_RETRY_BASE_DELAY = 1.0
_RETRY_JITTER = 0.5  # ±0.5s — 동시 retry 타이밍이 겹쳐 다시 503을 유발하지 않도록 분산


def _is_retryable_server_error(exc: Exception) -> bool:
    """5xx (model overloaded 등) 서버 측 일시 오류만 retry 대상으로 한다."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return isinstance(code, int) and 500 <= code < 600


async def _generate_with_retry(
    client: Any,
    *,
    config: types.GenerateContentConfig,
    contents: str,
    label: str,
) -> Any:
    """
    Gemini generate_content 호출에 exponential backoff retry 적용.
    503/500 계열 서버 오류만 재시도하며, validation/JSON/4xx 오류는 즉시 전파한다.
    """
    last_error: Exception | None = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            return client.models.generate_content(
                model=GEMINI_MODEL,
                config=config,
                contents=contents,
            )
        except Exception as e:
            if not _is_retryable_server_error(e):
                raise
            last_error = e
            if attempt >= _RETRY_MAX_ATTEMPTS:
                logger.error(
                    f"[gemini-retry] '{label}' attempt {attempt}/{_RETRY_MAX_ATTEMPTS} "
                    f"failed with server error, no retries left: {e}"
                )
                raise
            base_delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
            delay = max(0.0, base_delay + random.uniform(-_RETRY_JITTER, _RETRY_JITTER))
            logger.warning(
                f"[gemini-retry] '{label}' attempt {attempt}/{_RETRY_MAX_ATTEMPTS} "
                f"hit server error ({e}); retrying in {delay:.2f}s "
                f"(base={base_delay:.1f}s, jitter=±{_RETRY_JITTER:.1f}s)"
            )
            await asyncio.sleep(delay)
    raise last_error  # pragma: no cover


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


async def _generate_validated_package(
    issue: Dict[str, Any],
    max_retries: int = 2,
) -> Dict[str, Any]:
    """
    generate_exploration_package를 호출하되 mid/high reason이 종결어미로 끝나는지 검증.
    중간 절단된 응답이면 최대 max_retries회 재생성. 모두 실패하면 ValueError 발생 →
    호출부(run_weekly_generation)가 해당 이슈를 건너뛴다(저장하지 않음).
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
) -> List[IssuePackage]:
    """
    Orchestrates the full weekly generation pipeline:
    1. Cluster news into 9 issues
    2. Generate exploration packages for each issue
    3. Return validated IssuePackage objects
    """
    week_date = _get_current_week_date()

    logger.info(f"Starting weekly generation for week: {week_date}")
    logger.info(f"Input news items: {len(news_items)}")

    # Step 1: Cluster and tag
    issue_dicts = await cluster_and_tag_issues(news_items)

    if not issue_dicts:
        raise ValueError("Gemini returned no issues from clustering step")

    logger.info(f"Clustered into {len(issue_dicts)} issues")

    # Step 2: Generate exploration packages for each issue
    issue_packages: List[IssuePackage] = []

    for i, issue_dict in enumerate(issue_dicts):
        try:
            logger.info(
                f"Generating package {i+1}/{len(issue_dicts)}: {issue_dict.get('title', '')}"
            )
            package = await _generate_validated_package(issue_dict)
            issue_package = _build_issue_package(issue_dict, package, week_date)
            issue_packages.append(issue_package)
        except Exception as e:
            logger.error(
                f"Failed to generate package for issue '{issue_dict.get('title', '')}': {e}"
            )
            # Continue with remaining issues rather than failing entirely
            continue

    logger.info(
        f"Weekly generation complete: {len(issue_packages)} packages generated"
    )
    return issue_packages
