# 05. 발행 (반자동 마크다운 · Approve 채널 · 카드)

> 티스토리 Open API는 2024년 종료되었습니다. 블로그 발행은 **마크다운 파일 수동 붙여넣기**로 합니다.

## Approve 채널 (`NOTIFY_CHANNEL`)

`MVP_MODE=draft` 일 때 흐름:

1. 브리핑 준비  
2. **로컬 카드 PNG 렌더** (`run_dir/cards/`)  
3. `NOTIFY_SEND_AT`(예: `07:50`, Asia/Seoul)까지 대기 후 초안 + **슬라이드 이미지** 발송  
4. **이미지를 확인한 뒤** Approve / Skip  

`NOTIFY_SEND_AT`이 비어 있으면 준비 즉시 발송하고, 이미 지난 시각이면 대기 없이 보냅니다.  
구현: [`scripts/notify/`](../scripts/notify/).

| `NOTIFY_CHANNEL` | 동작 |
|------------------|------|
| (미설정) | Discord(주력) → telegram → slack → cli |
| `discord` | 슬라이드 PNG 첨부 + ✅ / ⏭ 리액션 |
| `telegram` | 슬라이드 사진(media group) + 인라인 Approve/Skip |
| `slack` | 슬라이드 파일 업로드 + ✅ / ⏭ 리액션 |
| `cli` | 터미널 `approve` / `skip` (+ 로컬 이미지 경로 출력) |
| `auto` | 대기 없이 승인 (로컬 스모크) |

공통 타임아웃: `APPROVE_TIMEOUT_SEC` (기본 900초).

### 미리보기에 포함

- 제목, 시장 한줄, 선정 뉴스, 슬라이드 headline
- **카드 PNG 첨부** (생성 실패 시 텍스트만 + 경고)
- 「슬라이드 이미지를 확인한 뒤 Approve」 안내
- Approve / Skip 조작법

| 선택 | 동작 |
|------|------|
| Approve | `briefing.md` 저장 (+ 채널에 md 첨부) → `PUBLISH_CARDS=1`이면 R2/인스타 (Approve 때 쓴 PNG 재사용) → `seen_urls` |
| Skip | 종료. `seen_urls` 미기록 |
| 타임아웃 | Skip과 동일 |

마크다운 저장 성공 시 `seen_urls`에 insert합니다. 인스타만 실패해도 마크다운·`seen_urls`는 유지하고 단계 알림을 보냅니다.

### Discord 설정 (주력)

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 앱·Bot 생성 → `DISCORD_BOT_TOKEN`
2. Bot 권한: `Send Messages`, `Attach Files`, `Add Reactions`, `Read Message History`
3. 서버에 봇 초대 후 **텍스트 채널** ID → `DISCORD_CHANNEL_ID`
4. `.env`에 `NOTIFY_CHANNEL=discord` (또는 토큰만 넣고 자동 선택)

> **주의:** `DISCORD_CHANNEL_ID`에는 **텍스트 채널의 숫자 ID**를 넣어야 합니다. Discord에서 Developer Mode를 켠 뒤 채널 우클릭 → **Copy Channel ID**로 복사하세요.  
> 카테고리 ID를 넣으면 `Cannot send messages in a non-text channel`(400)이 납니다.

스모크: `uv run python scripts/smoke_discord.py`

### Telegram 설정

스모크: `uv run python scripts/smoke_telegram.py`  
(호환) `TELEGRAM_APPROVE_MODE` 도 인식하나 **`NOTIFY_CHANNEL`이 우선**입니다.

### Slack 설정

1. Slack 앱 생성 → Bot Token (`SLACK_BOT_TOKEN`, `xoxb-…`)
2. 스코프 예: `chat:write`, `channels:history`, `reactions:read`, `reactions:write`, `files:write`
3. 채널에 봇 `/invite` 후 `SLACK_CHANNEL_ID`
4. `NOTIFY_CHANNEL=slack`

스모크: `uv run python scripts/smoke_slack.py`  
Approve는 Discord와 같이 **리액션**으로 받습니다 (공개 Request URL 없이 동작).

---

## 반자동 블로그 (Markdown)

| 파일 | 용도 |
|------|------|
| `briefing.md` | 에디터에 붙여넣기 (권장) |
| `briefing.html` | HTML이 필요할 때 |
| `briefing.json` | LLM 원본 구조 |

---

## 카드뉴스 / Instagram

카드 슬라이드·인스타 게시글 본문은 [`scripts/cards/`](../scripts/cards/) OOP 패키지가 조립합니다.

| 모듈 | 역할 |
|------|------|
| `CardAssembler` | cover / story / disclaimer 슬라이드 |
| `InstagramCaptionBuilder` | 게시글 본문(훅·포인트·CTA·면책) + 해시태그 |
| `CardRenderer` | HTML·PNG·`caption.txt` / `instagram_post.txt` |

### 템플릿 묶음 카탈로그

상세(루트 HTML vs `editorial/`, 재사용 원리, 새 템플릿 추가): **[09. 카드 템플릿](09-card-templates.md)**.

경제/사회 뉴스용 템플릿 정의는 [`scripts/cards/bundles/`](../scripts/cards/bundles/)에 JSON으로 저장합니다.

| id | 이름 | 장수 | 비고 |
|----|------|------|------|
| `editorial_carousel` | 에디토리얼 UI 템플릿 | 8 | **1080×1350 재사용 UI** (플레이스홀더만) |
| `why_cause_impact` | Why→원인→영향→전망 | 8 | 콘텐츠 예시 추천 |
| `myth_vs_truth` | 오해 vs 진실 | 7 | |
| `five_min_class` | 5분 경제 교실 | 6 | |
| `numbers` | 숫자로 보는 경제 | 6 | |
| `storytelling` | 스토리텔링 경제 | 6 | |
| `daily_briefing` | 오늘의 이슈 브리핑 | 2~10 (권장 5~7) | 기존 MVP 호환 |

에디토리얼 UI (`templates/cards/editorial/`): Info/Number/Quote/Impact Card, Timeline, Flow, Highlight Box 등. 실제 뉴스 문구 없이 플레이스홀더만 포함. **파이프라인 발행 경로는 MVP 1080×1080**을 씁니다.

```bash
uv run python scripts/preview_cardnews.py --list-bundles
```

### 로컬 미리보기 (R2 / IG 불필요)

```bash
docker compose up -d browserless   # PNG가 필요할 때 (또는 로컬 Chrome)
uv run python scripts/preview_cardnews.py --bundle editorial_carousel
# → output/cardnews-preview/
```

과거 파이프라인 런의 `briefing.json`으로 카드를 다시 뽑을 때:

```bash
uv run python scripts/preview_cardnews.py --from-run output/<YYYYMMDD_HHMMSS>
```

### 인스타 게시글 본문

```text
{브랜드} · {YYYY.MM.DD}
{후킹 한 줄}

오늘의 포인트
1) …
2) …

자세한 해설은 프로필 링크·블로그 브리핑에서 이어갑니다.

※ 정보 안내용이며 투자 권유가 아닙니다.

#경제뉴스 #증시 …
```

`full_text`는 Graph API 한도(2100자)에 맞춰 자릅니다. IG 미연동 시 `instagram_post.txt`를 수동 복붙하면 됩니다.

### 파이프라인 (`PUBLISH_CARDS`)

- **draft:** Approve **전**에 항상 로컬 카드 PNG를 만들어 채널에 첨부합니다.
- **`PUBLISH_CARDS=1`:** Approve **후** 같은 PNG로 R2 업로드 → Instagram 캐러셀(2–10장). 기본 `0`이면 마크다운만.
- R2/IG가 없어도 Approve 미리보기용 로컬 `run_dir/cards/`는 남습니다.

발행(호스팅·Graph) 로직은 [`scripts/publish/`](../scripts/publish/)에 있습니다.

| 모듈 | 역할 |
|------|------|
| `PublishConfig` | `PUBLISH_CARDS`, R2_*, IG_*, Meta Graph 버전 |
| `R2Uploader` | PNG → Cloudflare R2 공개 HTTPS URL |
| `InstagramCarouselPublisher` | children → CAROUSEL → status poll → `media_publish` |
| `PublishCardsPipeline` | Approve 후 R2 + 인스타 오케스트레이션 |

논리 테스트(실제 Meta/R2/채널 호출 없음):

```bash
uv run python -m unittest tests.test_instagram_publish tests.test_notify_approve tests.test_run_publish -v
```

다음: [06. 설치·설정](06-setup.md)
