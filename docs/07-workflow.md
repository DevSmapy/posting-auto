# 07. 워크플로 (Python MVP · n8n 후속)

## 실행 본체

현재 **실행 가능한 MVP**는 호스트 Python입니다.

```bash
uv sync
MVP_MODE=draft uv run python scripts/mvp_pipeline.py
# 또는
./scripts/run_draft.sh
```

로컬에서 기능 브랜치를 받을 때:

```bash
git fetch origin
git checkout -t origin/<feature-branch>
```

n8n UI 네이티브 워크플로(`workflows/econ-briefing-daily.json`)는 **후속**입니다.  
스케줄은 macOS/Linux cron + `scripts/cron_run_draft.sh` / `run_draft.sh`를 쓰는 것을 권장합니다.

## Python draft 순서 (2단계 게이트)

| # | 단계 | 역할 |
|---|------|------|
| 1 | Schedule / Manual | 평일 아침 등 |
| 2 | Google News RSS | BUSINESS + NATION |
| 3 | 창 필터 | `NEWS_WINDOW_MODE=since_prev_day_hour` (전일 15:00~now, KST) |
| 4 | Postgres `seen_urls` | 이미 쓴 URL 제외 |
| 5 | Content loop | Ollama 랭킹+layered story → `attempts/content-NN/` |
| 6 | ① 내용 게이트 | 텍스트만. ✅ Approve / 🔀 Rerank / ✍️ Rewrite (`CONTENT_RETRY_MAX`) |
| 7 | Render loop | 선택 `briefing.json` → `renders/render-NN/cards/` PNG |
| 8 | ② 렌더 게이트 | 이미지 확인. ✅ Approve / 🔁 Re-render (`RENDER_RETRY_MAX`) |
| 9a | Approve | `briefing.md` 저장 (블로그 수동 붙여넣기) |
| 9b | Postgres | **즉시** `seen_urls` insert (알림·IG 실패와 무관; 기록 삭제 없음) |
| 9c | `PUBLISH_CARDS=1` | 동일 PNG → R2 → (`PUBLISH_MODE`) Instagram carousel |
| 9d | `final/publish_ready/` | 카드 PNG·캡션·manifest 패키지 (나중에 CLI/n8n 게시) |
| 10 | Notify | 결과 / 단계 실패·부분스킵 알림 |
| 11 | ③ Cleanup ask | 확정본만 유지(삭제 책임 경고) / 전부 보관. 타임아웃→확정본만 |

Rerank는 이번 run의 이전 content attempt URL을 제외한 뒤 재랭킹한다. Rewrite는 같은 `picked`로 스토리만 재생성한다.  
남은 후보가 없으면 Rerank는 차감 없이 내용 게이트를 다시 띄운다. 재생성 도중 실패하면 차감분도 복구한다.  
재시도 소진 시 `seen_urls` 없이 중단한다.  
내용/렌더 게이트 **타임아웃** 시 run을 `parked`로 남기고 `./scripts/resume_draft.sh output/<run_id>`로 이어서 게이트를 연다 (`APPROVE_TIMEOUT_SEC` 기본 3600, 만료 전 `APPROVE_REMINDER_SEC` 재알림).

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
- 타임아웃/소진 시 미기록; 마크다운 저장 성공 시 insert (`ig_media_id`는 있을 때만)

## 에러 처리

- R2/인스타 단계 실패 → 채널에 `[R2/인스타 실패] …` 등 단계 알림
- 마크다운만 성공 / 인스타만 실패 등 **부분 성공** 명시
- 최상위 예외 → `[경제브리핑 실패] …`

## n8n (후속)

네이티브 노드로 옮길 때의 참고 순서: Schedule → RSS → Code → Ollama HTTP → Execute Command(`run_draft.sh`) 또는 단계별 HTTP.  
[`code-nodes/`](../workflows/code-nodes/) 샘플의 “당일 캘린더” 필터는 Python MVP의 `since_prev_day_hour`와 **다릅니다** — 샘플을 쓸 때 창 로직을 맞추세요.

다음: [08. 로드맵·운영](08-roadmap.md)
