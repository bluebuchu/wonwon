# 주간 탐구 이슈 서비스 API 명세

Base URL: `http://localhost:8000`

---

## 시스템

### `GET /health`
서버 상태 확인.

**응답:**
```json
{
  "status": "healthy",
  "service": "Korean High School Exploration Topic Service",
  "scheduler_running": true,
  "next_generation": "2026-03-28T17:00:00+09:00"
}
```

---

## 이슈 조회

### `GET /api/weeks`
저장된 주차 목록 반환.

**응답:**
```json
{
  "weeks": ["2026-03-24", "2026-03-17"],
  "total": 2
}
```

---

### `GET /api/issues/latest`
가장 최근 주차의 이슈 반환.

**쿼리 파라미터:**
| 파라미터 | 타입 | 설명 |
|--------|------|------|
| `track` | string (optional) | `인문사회` \| `자연공학` \| `의약생명` |

**응답:** `IssueListResponse`

---

### `GET /api/issues`
특정 주차 이슈 반환 (기본값: 최신 주차).

**쿼리 파라미터:**
| 파라미터 | 타입 | 설명 |
|--------|------|------|
| `week` | string (optional) | `YYYY-MM-DD` 형식 |
| `track` | string (optional) | `인문사회` \| `자연공학` \| `의약생명` |

**응답:** `IssueListResponse`

---

### `GET /api/issues/{issue_id}`
이슈 단건 상세 조회.

**응답:** `IssuePackage`

---

## 생성 트리거

### `POST /api/generate`
수동으로 생성 파이프라인 실행 (RSS 수집 → Claude AI 생성 → DB 저장).
소요 시간: 1~3분.

**응답 (성공):**
```json
{
  "status": "success",
  "count": 9,
  "week_date": "2026-03-24",
  "message": null
}
```

**응답 (이미 실행 중 - 409):**
```json
{ "detail": "Generation already in progress" }
```

---

## Mock 데이터 (프론트엔드 개발용)

실제 Claude AI 생성 없이 하드코딩된 9개 이슈를 반환. 프론트엔드 UI 개발에 사용.

### `GET /api/mock/issues`
Mock 이슈 목록.

**쿼리 파라미터:**
| 파라미터 | 타입 | 설명 |
|--------|------|------|
| `track` | string (optional) | `인문사회` \| `자연공학` \| `의약생명` |

### `GET /api/mock/issues/latest`
Mock 최신 이슈 (위와 동일).

### `GET /api/mock/issues/{issue_id}`
Mock 이슈 단건 조회.

**Mock 이슈 ID 목록:**
- `mock-hs-001` ~ `mock-hs-003` (인문사회)
- `mock-ne-001` ~ `mock-ne-003` (자연공학)
- `mock-ml-001` ~ `mock-ml-003` (의약생명)

---

## 데이터 스키마

### IssueListResponse
```json
{
  "issues": [ IssuePackage ],
  "total": 9,
  "week_date": "2026-03-24"
}
```

### IssuePackage
```json
{
  "id": "uuid",
  "week_date": "2026-03-24",
  "title": "이슈 제목",
  "track": "인문사회",
  "summary": "구조적 요약 2-4문장",
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"],
  "sources": [
    { "outlet": "KBS", "url": "https://..." }
  ],
  "mid_topic": ExplorationTopic,
  "high_topic": ExplorationTopic,
  "created_at": "2026-03-24T17:00:00"
}
```

### ExplorationTopic
```json
{
  "topic": "탐구 주제 (질문 형식)",
  "reason": "탐구 선택 이유 (150-350자)",
  "grade_guide": {
    "grade1": "1학년 탐구 방향 (1-2문장)",
    "grade2": "2학년 탐구 방향 (1-2문장)",
    "grade3": "3학년 탐구 방향 (1-2문장)"
  },
  "level": "중"
}
```

`level` 값: `"중"` (중급) 또는 `"상"` (고급)

---

## CORS

개발 환경에서는 `*` (모든 오리진 허용).
`.env`의 `CORS_ORIGINS`로 프로덕션 환경에서 제한 가능.

기본 허용 오리진:
- `http://localhost:5173` (Vite 프론트엔드)
- `http://localhost:3000`

---

## 서버 실행

```bash
cd C:\won\backend

# 1. .env 파일에 API 키 설정
# ANTHROPIC_API_KEY=sk-ant-...

# 2. 서버 기동 (개발)
python3 -m uvicorn main:app --reload --port 8000

# Swagger UI: http://localhost:8000/docs
```
