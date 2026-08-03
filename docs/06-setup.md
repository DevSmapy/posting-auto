# 06. 설치 · 설정

## 사전 준비 체크리스트

### 공통

- [ ] Docker Desktop
- [ ] 여유 RAM: `14b` 기준 16GB+ 권장 (`7b`는 더 낮아도 가능)

### Ollama (Docker)

**A) 이 프로젝트 Compose가 ollama를 소유할 때** (`--profile full`, 기존 컨테이너 없을 때만):

- [ ] `docker compose --profile full up -d ollama`
- [ ] `docker compose exec ollama ollama pull qwen2.5:14b`
- [ ] `./scripts/smoke_ollama.sh` (호스트 → `127.0.0.1:11434`)

**B) 이미 떠 있는 외장 Ollama를 재사용할 때** (기본 MVP 경로 — Compose로 start/exec 하지 않음):

- [ ] 기존 컨테이너가 `:11434`에서 응답하는지 확인 (`curl http://127.0.0.1:11434/api/tags`)
- [ ] 모델 없으면 호스트에서 pull: `curl -N http://127.0.0.1:11434/api/pull -d '{"name":"qwen2.5:14b"}'`
- [ ] `./scripts/smoke_ollama.sh`

### 티스토리 / 블로그

- [x] Open API 종료 → **반자동 마크다운** (`briefing.md` 수동 붙여넣기)
- [ ] (운영) Approve 후 에디터에 붙여넣기 습관화

### Instagram / Meta

- [ ] Instagram 프로페셔널(비즈니스/크리에이터) 계정 + **연결된 Facebook Page**
- [ ] Meta 앱 + Content Publishing
- [ ] 로그인·권한 (택 1):
  - **Facebook Login for Business:** `instagram_content_publish` (+ 필요 시 `pages_read_engagement`)
  - **Business Login for Instagram:** `instagram_business_content_publish` (+ 필요 시 `pages_read_engagement`)
- [ ] `IG_USER_ID`, **long-lived** Page/IG `META_ACCESS_TOKEN`

> 인스타 연동이 준비 중 가장 오래 걸리는 구간입니다.

### Discord (권장 Approve 채널 · 주력)

- [ ] Developer Portal Bot → `DISCORD_BOT_TOKEN`
- [ ] **텍스트 채널** ID → `DISCORD_CHANNEL_ID` (카테고리 ID 금지) + 봇 초대 (`View Channel` · Send · Attach Files · React · History; `View Channel`은 채널 상속 시 암묵 부여될 수 있음)
- [ ] `NOTIFY_CHANNEL=discord` (또는 자동 선택)
- [ ] `uv run python scripts/smoke_discord.py`

### Telegram

- [ ] BotFather 봇 → `TELEGRAM_BOT_TOKEN`
- [ ] `TELEGRAM_CHAT_ID` + 봇에게 `/start`
- [ ] `uv run python scripts/smoke_telegram.py`

### Slack

- [ ] Slack 앱 Bot Token → `SLACK_BOT_TOKEN`
- [ ] 채널에 봇 invite → `SLACK_CHANNEL_ID`
- [ ] `NOTIFY_CHANNEL=slack`
- [ ] `uv run python scripts/smoke_slack.py`

### Postgres / seen_urls

- [x] `docker compose up -d postgres`
- [x] `uv run python scripts/smoke_seen_urls.py`

### Cloudflare R2

- [ ] 버킷 + 공개(또는 커스텀 도메인) base URL
- [ ] S3 호환 액세스 키

---

## 환경 변수

전체 목록은 [`.env.example`](../.env.example)을 보세요. (`cp .env.example .env`)

### 스토리지 경로 (요약)

| 변수 | 기본 경로 |
|------|-----------|
| `IMAGE_DIR` | `/Volumes/WD_BLACK/Careers/DockerData/images` |
| `POSTGRES_DATA_PATH` | `/Volumes/WD_BLACK/Careers/DockerData/posting-auto/postgres` |
| `N8N_DATA_PATH` | `/Volumes/WD_BLACK/Careers/DockerData/n8n_data` |
| `OLLAMA_IMAGE_DIR` | `"/Volumes/Extreme SSD/DockerData/images"` (따옴표 필수) |
| `OLLAMA_DATA_PATH` | `"/Volumes/Extreme SSD/DockerData/ollama_data"` (따옴표 필수) |

> `Extreme SSD`처럼 경로에 공백이 있으면 `.env`에서 **반드시 `"..."`로 감싸야** 합니다.  
> 따옴표 없이 `source .env` 하면 `/Volumes/Extreme` 까지만 변수에 들어가고 깨집니다.

Ollama API: 컨테이너용 `OLLAMA_BASE_URL=http://host.docker.internal:11434`,  
호스트 스크립트용 `OLLAMA_HOST_URL=http://127.0.0.1:11434`.

`.env`는 git에 올리지 않습니다.

---

## 로컬 실행

자세한 절차: [00. MVP 빠른 시작](00-mvp-quickstart.md)

```bash
cp .env.example .env
uv sync

./scripts/smoke_ollama.sh
docker compose up -d postgres browserless
MVP_MODE=dry_run uv run python scripts/mvp_pipeline.py
```

의존성·가상환경은 **uv** 기준입니다 (`pyproject.toml`).  
논리 테스트만 할 때: `uv sync` 후 `uv run python -m unittest discover -s tests -v`  
(`requirements.txt`는 호환용 미러이며, 신규 설치는 `uv sync`를 쓰세요.)

### compose 서비스 (기본)

| 서비스 | 역할 | 포트 | 비고 |
|--------|------|------|------|
| `postgres` | DB + `seen_urls` | `5433` | WD_BLACK 데이터 |
| `browserless` | 카드 스크린샷 | `3000` | |
| `n8n` / `ollama` | — | — | 기존 컨테이너 재사용 (`full` 프로필만) |

다음: [07. 워크플로](07-workflow.md)
