# 07. n8n 워크플로

워크플로 이름(예정): `econ-briefing-daily`  
파일(예정): `workflows/econ-briefing-daily.json`

## 노드 순서

| # | 단계 | 역할 |
|---|------|------|
| 1 | Schedule | 평일 `30 7 * * 1-5`, `Asia/Seoul` |
| 2 | RSS Read ×2 | `GNEWS_BUSINESS_RSS`, `GNEWS_NATION_RSS` |
| 3 | Code | merge, `topic` 태그, `feed_rank`, `cluster_size` 계산 |
| 4 | Code/Filter | 당일 `pubDate` (Asia/Seoul) |
| 5 | Postgres | `seen_urls` 제외 |
| 6 | IF | 후보 0건 → Telegram “오늘 스킵” 종료 |
| 7 | 상위 N 슬라이스 | `NEWS_MAX_CANDIDATES` (기본 20) |
| 8 | HTTP Ollama | 중요도 JSON |
| 9 | Code | 파싱·정렬·상위 `NEWS_PICK_COUNT`(5) |
| 10 | HTTP Ollama | 브리핑 JSON |
| 11 | Code | 스키마 검증, 티스토리 HTML 조립 |
| 12 | Telegram | 초안 + Approve / Skip |
| 13 | IF Skip | 종료 |
| 14a | HTTP | 티스토리 `post/write` |
| 14b | Loop | 카드 HTML → Browserless → R2 |
| 15 | HTTP | IG carousel items → parent → poll → publish |
| 16 | Postgres | `seen_urls` insert |
| 17 | Telegram | 결과 URL / 실패 단계 |

## `seen_urls` (예정 SQL)

```sql
CREATE TABLE IF NOT EXISTS seen_urls (
  url_hash CHAR(64) PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  used_in_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tistory_post_id TEXT,
  ig_media_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_seen_urls_used_at ON seen_urls (used_in_run_at DESC);
```

- `url_hash`: 정규화 URL의 SHA-256
- Skip 시 기본 미기록, 발행 성공 시에만 insert

## 에러 처리

- 단계별 실패 → Telegram에 **단계명 + 상태코드 + 메시지**
- 티스토리만 성공 / 인스타만 실패 등 부분 성공도 명시
- Ollama JSON 파싱 실패 → 1회 재시도 후 에러 알림

다음: [08. 로드맵·운영](08-roadmap.md)
