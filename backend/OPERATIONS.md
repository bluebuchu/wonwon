# Operations — won 주간 이슈 생성 cron

이 문서는 `/api/cron/generate` 운영을 위한 런북이다. 자동 실행은 Vercel Cron이 매주
금요일 17:00 KST에 트리거하며, 그 외 시점의 수동 개입 절차를 정리한다.

---

## 1. 수동 실행

엔드포인트: `GET https://www.schoolwins.kr/api/cron/generate`
인증: `Authorization: Bearer $CRON_SECRET` (Vercel 환경변수)

```bash
curl -sS -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $CRON_SECRET" \
  https://www.schoolwins.kr/api/cron/generate
```

응답 예시 (모든 정상/강등 경로는 HTTP 200, 응답 본문 `status` 필드로 구분):

```jsonc
// 전체 성공
{"status":"success","mode":"normal","week_date":"YYYY-MM-DD",
 "partial_success":false,"generated_count":9,"failed_count":0,
 "raw_fallback_count":0,"failed_titles":[],"reason":null}

// 부분 성공 (AI 일부 실패)
{"status":"partial_success","mode":"normal","week_date":"YYYY-MM-DD",
 "partial_success":true,"generated_count":4,"failed_count":5,
 "raw_fallback_count":0,"failed_titles":["...","..."],"reason":null}

// AI 전수 실패 → RSS 원문 강등 발행
{"status":"success","mode":"raw_fallback","week_date":"YYYY-MM-DD",
 "partial_success":false,"generated_count":0,"failed_count":9,
 "raw_fallback_count":6,"failed_titles":[...],"reason":"all_issues_failed"}

// Clustering 실패 → RSS 원문 강등 발행
{"status":"success","mode":"raw_fallback","week_date":"YYYY-MM-DD",
 "partial_success":false,"generated_count":0,"failed_count":0,
 "raw_fallback_count":6,"failed_titles":[],"reason":"clustering_failed"}

// RSS 자체가 0건 (발행 불가)
{"status":"skipped","reason":"no_news_items","mode":null, ...}

// 인증 실패
{"detail":"Unauthorized cron call."}                              // HTTP 401

// 환경변수 누락 / DB save 실패 (운영자 알림 신호)
{"detail":"stage=save: ..."}                                      // HTTP 500
```

`CRON_SECRET`은 Vercel 대시보드 → Project → Settings → Environment Variables에서
확인. 셸에 export 되어 있지 않으면 한 줄 inline으로 넣는다.

```bash
CRON_SECRET=<paste> curl -sS -H "Authorization: Bearer $CRON_SECRET" \
  https://www.schoolwins.kr/api/cron/generate
```

같은 `week_date`로 재실행하면 `save_batch`가 기존 issues를 DELETE 후 재삽입하므로
정상 결과로 안전하게 덮어쓸 수 있다. **단, partial/raw_fallback 결과도 저장되므로
이미 정상 batch가 있는 주에 503 부분 실패 또는 raw fallback 재실행이 들어가면
축소판/원문판으로 덮여쓰일 수 있다** — 이번 주에 정상 batch가 이미 들어가 있는지
확인 후 재실행할 것. 반대로, raw_fallback이 저장된 주차에 AI 복구 후 재실행하면
정상 9개 배치로 자동 덮어쓰여 복구된다.

### 1.1 2026-05-22 누락분 수동 재발행

2026-05-22 17:00:36 KST cron이 `stage=generate error=503 UNAVAILABLE`로 실패해
발행이 누락됨. 본 patch 배포 후 다음 절차로 복구:

```bash
# (1) 최신 코드 배포 — Vercel은 main push 시 자동 배포
git push origin main

# (2) Production deployment가 "Ready" 상태가 된 것을 Vercel 대시보드에서 확인

# (3) 수동 재실행
curl -sS -w "\nHTTP %{http_code}\n" \
  -H "Authorization: Bearer $CRON_SECRET" \
  https://www.schoolwins.kr/api/cron/generate

# (4) 응답에서 week_date="2026-05-22" 확인
#     - status="success" / mode="normal"     → AI 복구 완료, 9개 정상 발행
#     - status="partial_success"             → 일부 503 잔존, 며칠 뒤 재실행해 9개로 보강
#     - status="success" / mode="raw_fallback" → Gemini 여전히 불안. RSS 6개로 우선 발행됨
#     - status="skipped" / reason="no_news_items" → RSS 자체 0건 (드문 케이스)
```

`_get_current_week_date()`는 호출 시점 UTC 기준으로 "이번 주 금요일"을 계산하므로,
2026-05-29 이전에 수동 실행하면 자동으로 `week_date="2026-05-22"`로 저장된다.
2026-05-29 (다음 cron) 이후엔 그 주차로 잡히므로 누락분 복구는 그 전에 처리할 것.

---

## 2. Gemini 503 발생 시 재시도 권장 시점

코드 측 retry는 이미 적용되어 있다.
- 호출 1회당 최대 **3 attempt**, exponential backoff(1s → 2s) + ±0.5s jitter
- 따라서 한 번의 cron 실행은 503에 대해 약 3s 정도 자체 재시도 후 raw fallback으로 강등 발행한다
- raw fallback은 추가 AI 호출이 없으므로 비용 0

`attempt 3/3`까지 모두 503이면 그 호출은 raw fallback 경로(클러스터링) 또는
이슈별 continue 경로(개별 패키지)로 흡수된다. 사용자에겐 어떤 형태로든 발행이 노출되며,
운영자는 로그의 `mode=raw_fallback` / `failed_titles=[...]`로 AI 장애를 식별한다.

| 첫 실패 후 경과 | 권장 액션 |
|---|---|
| ~5분 이내 | 즉시 재실행 의미 적음 (같은 부하 윈도우에 묶일 가능성). 대기 |
| 10–30분 | 수동 재실행 1차 시도 — 성공 시 raw fallback이 정상 배치로 덮어써짐 |
| 30–60분 | 재실행 2차 시도. 여전히 503이면 Google AI Studio 상태 확인 |
| 1시간+ | 모델 자체 장애 가능성. 별도 PR로 paid fallback 또는 OpenAI 도입 검토 |

자동 재실행 루프는 두지 않는다 — 같은 모델/같은 키로 짧은 간격에 두드리면 부하만 키운다.

---

## 3. 로그 확인 위치

Vercel 대시보드 경로
1. Project (`wonwon`) → Deployments
2. 가장 최근 Production deployment 선택
3. 상단 탭 `Functions` → `Logs` (또는 좌측 사이드바 `Logs`)
4. 필터 `path = /api/cron/generate` 또는 검색어 `[Cron]`로 좁히기
5. 시간 범위: cron 실행 시각 기준 ±10분

장기 로그(과거 invocation)는 Vercel Logs 보존 기간(플랜에 따라 1일~30일) 내에서만
조회 가능하다. 장애 후 빠르게 캡처해 둘 것.

---

## 4. 성공 / 실패 판단 기준

### 4.1 전체 성공 (mode=normal, status=success)

```
[Cron] Weekly generation triggered at <iso>
[Cron][news] collected N items
[Cron][generate] starting (input=N items)
Gemini clustered 9 issues from M news items
Generating package 1/9: ...
... (9회)
Weekly generation complete: mode=normal partial_success=False generated=9 failed=0 attempted=9 per_track={'인문사회':3,'자연공학':3,'의약생명':3} failed_titles=[]
[Cron][generate] mode=normal partial_success=False generated=9 failed=0 raw_fallback=0 attempted=9 reason=None failed_titles=[]
[Cron][save] writing batch week_date=YYYY-MM-DD mode=normal generated=9 failed=0 raw_fallback=0
[Cron][done] status=success mode=normal week=YYYY-MM-DD generated=9 failed=0 raw_fallback=0 elapsed=Xs
```

### 4.2 부분 성공 (mode=normal, status=partial_success)

```
Failed to generate package for '...': ...   ← 일부 503 (반복)
Weekly generation complete: mode=normal partial_success=True generated=4 failed=5 attempted=9 ...
[Cron][done] status=partial_success mode=normal week=YYYY-MM-DD generated=4 failed=5 raw_fallback=0 elapsed=Xs
```

HTTP 200. 사용자에겐 4개 이슈가 노출. AI 복구 후 같은 주차 재실행으로 9개로 덮어쓰기 가능.

### 4.3 Raw fallback — Clustering 실패 (mode=raw_fallback, reason=clustering_failed)

```
[gemini-retry] 'cluster_and_tag_issues' attempt 1/3 caught exception ...
[gemini-retry] 'cluster_and_tag_issues' attempt 2/3 ...
[gemini-retry] 'cluster_and_tag_issues' exhausted retries after 3/3: ...
[clustering] exhausted retries: ...
[raw-fallback] reason=clustering_failed count=6 attempted=0 failed_titles=[]
[Cron][done] status=success mode=raw_fallback week=YYYY-MM-DD generated=0 failed=0 raw_fallback=6 elapsed=Xs
```

HTTP 200. 사용자에겐 RSS 원문 6장 노출, placeholder text가 raw 모드임을 알려줌.

### 4.4 Raw fallback — Per-issue 전수 실패 (mode=raw_fallback, reason=all_issues_failed)

```
Gemini clustered 9 issues from M news items
Failed to generate package for '...': ...   ← 9회 반복
[generation] 0 succeeded out of 9; raw fallback 강등. failed_titles=[...]
[raw-fallback] reason=all_issues_failed count=6 attempted=9 failed_titles=[...]
[Cron][done] status=success mode=raw_fallback week=YYYY-MM-DD generated=0 failed=9 raw_fallback=6 elapsed=Xs
```

### 4.5 RSS 자체 0건 (status=skipped)

```
[Cron][news] collected 0 items
[Cron][news] no items collected — skipping (RSS empty)
```

HTTP 200, status=skipped. 발행할 원본 자체가 없는 케이스 — 발행 누락이 정상 동작.

### 4.6 진짜 장애 (HTTP 500)

```
[Cron][failed] stage=save elapsed=Xs error=...    ← DB 장애
[Cron][failed] stage=init elapsed=0.0s error=CRON_SECRET ...   ← 환경변수 누락
```

운영자 알림이 필요한 신호. AI 장애 경로는 더 이상 여기 도달하지 않는다.

### 판정 체크리스트

| 항목 | 기준 |
|---|---|
| HTTP 응답 | `200` (정상/강등 모두) 또는 `401`/`500` (의도된 실패) |
| `status` 필드 | `success` / `partial_success` / `skipped` |
| `mode` 필드 | `normal` / `raw_fallback` |
| `[Cron][done]` 라인 존재 | 필수 — status/mode/카운트로 품질 확인 |
| `partial_success=true` | AI 일부 503. 모델 회복 후 재실행으로 보강 가능 |
| `mode=raw_fallback` | AI 전수 실패. 운영자 알림 권장 (수동 재실행으로 복구) |
| `[Cron][failed]` 라인 존재 | 진짜 장애 (stage=save/news/init). 즉시 대응 필요 |
| `[gemini-retry] ... retryable=False` | retry 분류 실패. 진단 로그로 SDK 예외 형태 확인 |
| `attempt 3/3` 후 `exhausted retries` | 해당 호출은 raw fallback 또는 issue continue로 흡수됨 |
