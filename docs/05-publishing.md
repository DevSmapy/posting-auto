# 05. 발행 (티스토리 · 카드 · 인스타 · Telegram)

## Telegram 승인 게이트

`MVP_MODE=draft` 일 때 [`scripts/mvp_pipeline.py`](../scripts/mvp_pipeline.py)가 초안을 보낸 뒤 **Approve/Skip**을 기다립니다.

### 미리보기에 포함

- 제목, 시장 한줄
- 선정 뉴스 헤드라인 + 중요도 점수
- 카드 슬라이드 headline 목록
- **Approve / Skip** (인라인 버튼) 또는 `/approve` `/skip` 텍스트

| 선택 | 동작 |
|------|------|
| Approve | 티스토리 + 카드/인스타 진행 |
| Skip | 종료. `seen_urls` 미기록 (다음날 다시 후보 가능) |
| 타임아웃 | `TELEGRAM_APPROVE_TIMEOUT_SEC`(기본 900초) 후 Skip과 동일 |

| `TELEGRAM_APPROVE_MODE` | 동작 |
|-------------------------|------|
| (미설정) | 토큰 있으면 `telegram`, 없으면 `cli` |
| `telegram` | 인라인 버튼 + `getUpdates` 폴링 |
| `cli` | 터미널에 `approve` / `skip` 입력 |
| `auto` | 대기 없이 승인 (로컬 스모크) |

Approve 후 **발행 성공 시**에만 `seen_urls`에 insert (`scripts/seen_urls.py`, Postgres 우선·불가 시 SQLite).

스모크: `python scripts/smoke_telegram.py`

---

## 티스토리

- 문서: [티스토리 Open API](https://www.tistory.com/guide/api/manage/register)
- `POST` `https://www.tistory.com/apis/post/write`

| 파라미터 | 값 |
|----------|-----|
| `access_token` | `.env` |
| `blogName` | `.env` |
| `title` | 브리핑 `title` |
| `content` | 조립 HTML |
| `visibility` | `3` 테스트 → `0` 운영 |
| `tag` | `blog_tags` |

테스트 순서: 수동 비공개 → n8n 비공개 → 공개.

토큰 없이 발행 경로만 검증: `TISTORY_DRY_RUN=1` (API 미호출, 로컬 stub + `seen_urls` 기록).  
스모크: `python scripts/smoke_tistory.py`

---

## 카드뉴스 렌더

템플릿(예정):

- `templates/cards/cover.html`
- `templates/cards/slide.html`
- `templates/cards/disclaimer.html`

공통: 1080×1080, 큰 제목 + 짧은 본문, 브랜드/블로그명 푸터.

1. 슬라이드별 HTML 주입  
2. Browserless screenshot → PNG  
3. R2(S3 호환) 업로드 → 공개 URL  

인스타 Graph API는 **이미지 URL**이 필요하므로 R2(또는 S3)를 MVP 기본으로 둡니다.

---

## Instagram 캐러셀

전제: 프로페셔널 계정 + Facebook 페이지 + Meta 앱 Content Publishing.

1. 이미지마다 `POST /{IG_USER_ID}/media` (`is_carousel_item=true`)  
2. 부모 `media_type=CAROUSEL` + `children` + `caption`  
3. 상태 `FINISHED` 폴링  
4. `POST /{IG_USER_ID}/media_publish`  

버전: `.env`의 `META_GRAPH_VERSION` (예: `v21.0`).

---

## 면책 문구 (고정)

> 본 콘텐츠는 정보 안내용이며 특정 종목의 매수·매도·투자를 권유하지 않습니다. 투자 판단과 책임은 독자 본인에게 있습니다.

블로그 하단·카드 마지막 슬라이드·인스타 캡션 중 최소 한 곳에 포함합니다.

다음: [06. 설치·설정](06-setup.md)
