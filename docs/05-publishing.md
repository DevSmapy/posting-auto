# 05. 발행 (반자동 마크다운 · Approve 채널 · 카드)

> 티스토리 Open API는 2024년 종료되었습니다. 블로그 발행은 **마크다운 파일 수동 붙여넣기**로 합니다.

## Approve 채널 (`NOTIFY_CHANNEL`)

`MVP_MODE=draft` 일 때 [`scripts/mvp_pipeline.py`](../scripts/mvp_pipeline.py)가 초안을 보낸 뒤 **Approve/Skip**을 기다립니다.  
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

## 카드뉴스 / Instagram (옵션)

`PUBLISH_CARDS=1` 일 때만 Approve 후 카드 렌더·R2·인스타를 시도합니다. 기본은 `0`(마크다운만).

다음: [06. 설치·설정](06-setup.md)
