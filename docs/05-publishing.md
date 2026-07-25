# 05. 발행 (반자동 마크다운 · Approve 채널 · 카드)

> 티스토리 Open API는 2024년 종료되었습니다. 블로그 발행은 **마크다운 파일 수동 붙여넣기**로 합니다.

## Approve 채널 (`NOTIFY_CHANNEL`)

`MVP_MODE=draft` 일 때 [`scripts/mvp_pipeline.py`](../scripts/mvp_pipeline.py)가 브리핑을 준비한 뒤, `NOTIFY_SEND_AT`(예: `07:50`, Asia/Seoul)까지 기다렸다가 초안을 보내고 **Approve/Skip**을 기다립니다. 비어 있으면 준비 즉시 발송하고, 이미 지난 시각이면 대기 없이 보냅니다.  
구현: [`scripts/notify/`](../scripts/notify/).

| `NOTIFY_CHANNEL` | 동작 |
|------------------|------|
| (미설정) | Discord 토큰 있으면 `discord` → 없으면 `telegram` → 없으면 `cli` |
| `discord` | 채널 메시지 + ✅ / ⏭ 리액션 폴링 |
| `telegram` | 인라인 버튼 + `getUpdates` 폴링 |
| `cli` | 터미널 `approve` / `skip` |
| `auto` | 대기 없이 승인 (로컬 스모크) |

공통 타임아웃: `APPROVE_TIMEOUT_SEC` (없으면 Telegram/Discord 개별 변수, 기본 900초).

### 미리보기에 포함

- 제목, 시장 한줄
- 선정 뉴스 헤드라인 + 중요도 점수
- 카드 슬라이드 headline 목록
- Approve / Skip 안내

| 선택 | 동작 |
|------|------|
| Approve | `output/<시각>/briefing.md` 저장 (+ 채널 알림; Discord는 파일 첨부) |
| Skip | 종료. `seen_urls` 미기록 |
| 타임아웃 | Skip과 동일 |

Approve 후 **마크다운 저장 성공 시**에만 `seen_urls`에 insert.

### Discord 설정

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 앱·Bot 생성 → `DISCORD_BOT_TOKEN`
2. Bot 권한: `Send Messages`, `Attach Files`, `Add Reactions`, `Read Message History` (해당 채널)
3. 서버에 봇 초대 후, **텍스트 채널** ID → `DISCORD_CHANNEL_ID`
4. `.env`에 `NOTIFY_CHANNEL=discord` (또는 토큰만 넣고 자동 선택)

> **주의:** `DISCORD_CHANNEL_ID`는 `#일반`처럼 **#으로 시작하는 텍스트 채널**이어야 합니다.  
> 카테고리(예: “채팅 채널” 폴더) ID를 넣으면 `Cannot send messages in a non-text channel`(400)이 납니다.  
> 개발자 모드 ON → 텍스트 채널 우클릭 → **채널 ID 복사**.

스모크: `python scripts/smoke_discord.py`  
Approve 후 채널에 `briefing.md` 파일이 첨부됩니다 (붙여넣기용).

### Telegram 설정

스모크: `python scripts/smoke_telegram.py`  
(호환) `TELEGRAM_APPROVE_MODE` 도 인식하나 **`NOTIFY_CHANNEL`이 우선**입니다.

### Slack

다음 단계. 인터페이스(`Notifier`)만 맞춰 두었고 어댑터는 아직 없습니다.

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

경제/사회 뉴스용 템플릿 정의는 [`scripts/cards/bundles/`](../scripts/cards/bundles/)에 JSON으로 저장합니다.

| id | 이름 | 장수 | 비고 |
|----|------|------|------|
| `why_cause_impact` | Why→원인→영향→전망 | 8 | **경제/사회 기본 추천** |
| `myth_vs_truth` | 오해 vs 진실 | 7 | |
| `five_min_class` | 5분 경제 교실 | 6 | |
| `numbers` | 숫자로 보는 경제 | 6 | |
| `storytelling` | 스토리텔링 경제 | 6 | |
| `daily_briefing` | 오늘의 이슈 브리핑 | 5~7 | 기존 MVP 호환 |

```bash
python scripts/preview_cardnews.py --list-bundles
```

### 로컬 미리보기 (R2 / IG 불필요)

```bash
docker compose up -d browserless   # PNG가 필요할 때 (또는 로컬 Chrome)
python scripts/preview_cardnews.py --bundle why_cause_impact
# → output/cardnews-preview/
#    slides.json, slide-*.html, slide-*.png(가능 시),
#    caption.txt, hashtags.txt, instagram_post.txt
```

PNG 백엔드: Browserless(`BROWSERLESS_URL`) → 실패 시 로컬 Chrome. 둘 다 없으면 HTML·캡션만 저장합니다.

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

`PUBLISH_CARDS=1`일 때만 Approve 후 카드 렌더·R2·인스타를 시도합니다. 기본은 `0`(마크다운만).  
R2/IG가 없어도 로컬 `run_dir/cards/`에 HTML·PNG·캡션은 남습니다.

다음: [06. 설치·설정](06-setup.md)
