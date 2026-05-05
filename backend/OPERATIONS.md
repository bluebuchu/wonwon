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

응답 예시
- 성공: `{"status":"success","count":9,"week_date":"YYYY-MM-DD"}` + `HTTP 200`
- 입력 부재: `{"status":"skipped","reason":"no news items"}` + `HTTP 200`
- 임계치 미달/스테이지 실패: `{"detail":"stage=generate: ..."}` + `HTTP 500`
- 인증 실패: `{"detail":"Unauthorized cron call."}` + `HTTP 401`

`CRON_SECRET`은 Vercel 대시보드 → Project → Settings → Environment Variables에서
확인. 셸에 export 되어 있지 않으면 한 줄 inline으로 넣는다.

```bash
CRON_SECRET=<paste> curl -sS -H "Authorization: Bearer $CRON_SECRET" \
  https://www.schoolwins.kr/api/cron/generate
```

같은 `week_date`로 재실행하면 `save_batch`가 기존 issues를 DELETE 후 재삽입하므로
정상 결과로 안전하게 덮어쓸 수 있다 (단, 임계치 가드 통과한 경우에만 저장된다).

---

## 2. Gemini 503 발생 시 재시도 권장 시점

코드 측 retry는 이미 적용되어 있다.
- 호출 1회당 최대 4 attempt, exponential backoff(1s → 2s → 4s) + ±0.5s jitter
- 따라서 한 번의 cron 실행은 503에 대해 약 7s 정도 자체 재시도 후 실패 처리된다

`attempt 4/4`까지 모두 503이면 모델 측 부하가 retry window보다 길게 지속된 상태다.
경험적 권장:

| 첫 실패 후 경과 | 권장 액션 |
|---|---|
| ~5분 이내 | 즉시 재실행 의미 적음 (같은 부하 윈도우에 묶일 가능성). 대기 |
| 10–30분 | 수동 재실행 1차 시도 |
| 30–60분 | 재실행 2차 시도. 여전히 503이면 Google AI Studio 상태 확인 |
| 1시간+ | 모델 자체 장애 가능성 → fallback 모델 도입 검토 (별도 PR) |

자동 재실행 루프는 두지 않는다 — 같은 모델/같은 키로 짧은 간격에 두드리면 부하만
키운다.

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

성공 시 로그 시퀀스 (최소 충족 라인)

```
[Cron] Weekly generation triggered at <iso>
[Cron][news] collected N items
[Cron][generate] starting (input=N items)
Gemini clustered 9 issues from M news items
Generating package 1/9: ...
Generated exploration package for issue: ...
... (9회 반복)
Weekly generation complete: total=9, per_track={'인문사회': 3, '자연공학': 3, '의약생명': 3}
[Cron][generate] produced 9 packages
[Cron][save] writing batch week_date=YYYY-MM-DD count=9
[Cron][done] saved 9 issues for week YYYY-MM-DD (elapsed=Xs)
```

부분 성공으로 임계치 미달 → 의도된 실패

```
Failed to generate package for issue '...': ...   ← 일부 패키지 실패
Threshold not met: total=4 (min=6), per_track={...}, deficient=[...]
[Cron][failed] stage=generate elapsed=Xs error=Threshold not met: ...
```

이 케이스는 **실패가 정상 동작**이다. DB의 기존 batch가 그대로 유지되어 사용자에게
지난 주 데이터가 계속 노출된다. 모델 회복 후 수동 재실행으로 같은 주차에 덮어쓰기.

503에 의한 단계 실패

```
[gemini-retry] 'cluster_and_tag_issues' attempt 1/4 caught exception (retryable=True) — type=google.genai.errors.ServerError code=503 ...
[gemini-retry] 'cluster_and_tag_issues' retrying in 1.23s (base=1.0s, jitter=±0.5s)
... (반복)
[gemini-retry] 'cluster_and_tag_issues' exhausted retries after 4/4: ...
[Cron][failed] stage=generate elapsed=Xs error=...
```

`retryable=True`로 표기되며 attempt 1~4가 모두 보이면 retry 자체는 정상 동작 중이다.

판정 체크리스트

| 항목 | 기준 |
|---|---|
| HTTP 응답 | `200` + `status=success` + `count >= 6` |
| `[Cron][done]` 라인 존재 | 필수 |
| `[Cron][failed]` 라인 존재 | 실패 (stage 필드로 원인 분리) |
| `Threshold not met` 라인 | 부분 성공 — 저장되지 않음, 정상적인 의도된 실패 |
| `[gemini-retry] ... retryable=False` | retry 분류 실패. 진단 로그(`type=...`, `code=...`)로 SDK 예외 형태 확인 후 코드 수정 필요 |
| `attempt 4/4` 후 `exhausted retries` | 모델 부하 지속. §2 절차에 따라 시간을 두고 재실행 |
