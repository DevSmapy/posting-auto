# 07. 워크플로 (Python MVP · n8n 후속)

## 실행 본체

현재 **실행 가능한 MVP**는 호스트 Python입니다.

```bash
uv sync
MVP_MODE=draft uv run python scripts/mvp_pipeline.py
# 또는
./scripts/run_draft.sh
```

n8n UI 네이티브 워크플로(`workflows/econ-briefing-daily.json`)는 **후속**입니다.  
스케줄은 macOS/Linux cron + `scripts/cron_run_draft.sh` / `run_draft.sh`를 쓰는 것을 권장합니다.

## Python draft 순서

| # | 단계 | 역할 |
|---|------|------|
| 1 | Schedule / Manual | 평일 아침 등 |
| 2 | Google News RSS | BUSINESS + NATION |
| 3 | 창 필터 | `NEWS_WINDOW_MODE=since_prev_day_hour` (전일 15:00~now, KST) |
| 4 | Postgres `seen_urls` | 이미 쓴 URL 제외 |
| 5 | Ollama 중요도·브리핑 | 또는 heuristic |
| 6 | 카드 PNG | Browserless/Chrome → `run_dir/cards/` |
| 7 | Notify Approve | Discord(주력) / Telegram / Slack — **이미지 확인 후** Approve/Skip |
| 8 | Skip | 종료, `seen_urls` 미기록 |
| 9a | Approve | `briefing.md` 저장 (블로그 수동 붙여넣기) |
| 9b | `PUBLISH_CARDS=1` | 동일 PNG → R2 → Instagram carousel |
| 10 | Postgres | `seen_urls` insert (마크다운 성공 시; IG 실패해도 기록) |
| 11 | Notify | 결과 / 단계 실패·부분스킵 알림 |

## `seen_urls`

스키마: [`init/01_seen_urls.sql`](../init/01_seen_urls.sql) · 런타임: [`scripts/seen_urls.py`](../scripts/seen_urls.py)

```sql
CREATE TABLE IF NOT EXISTS seen_urls (
  url_hash CHAR(64) PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  used_in_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tistory_post_id TEXT,
  ig_media_id TEXT
);
```

- `url_hash`: URL 문자열의 SHA-256 (현재 정규화 없음)
- Skip 시 미기록; 마크다운 저장 성공 시 insert (`ig_media_id`는 있을 때만)

## 에러 처리

- R2/인스타 단계 실패 → 채널에 `[R2/인스타 실패] …` 등 단계 알림
- 마크다운만 성공 / 인스타만 실패 등 **부분 성공** 명시
- 최상위 예외 → `[경제브리핑 실패] …`

## n8n (후속)

네이티브 노드로 옮길 때의 참고 순서: Schedule → RSS → Code → Ollama HTTP → Execute Command(`run_draft.sh`) 또는 단계별 HTTP.  
[`code-nodes/`](../workflows/code-nodes/) 샘플의 “당일 캘린더” 필터는 Python MVP의 `since_prev_day_hour`와 **다릅니다** — 샘플을 쓸 때 창 로직을 맞추세요.

다음: [08. 로드맵·운영](08-roadmap.md)
