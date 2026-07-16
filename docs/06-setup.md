# 06. 설치 · 설정

## 사전 준비 체크리스트

### 공통

- [ ] Docker Desktop
- [ ] 여유 RAM: `14b` 기준 16GB+ 권장 (`7b`는 더 낮아도 가능)

### Ollama (Docker)

- [ ] `docker compose up -d ollama` (또는 기존 Ollama 컨테이너 실행 중)
- [ ] `docker compose exec ollama ollama pull qwen2.5:14b`
- [ ] `./scripts/smoke_ollama.sh` (호스트 → `127.0.0.1:11434`)

### 티스토리 / 블로그

- [x] Open API 종료 → **반자동 마크다운** (`briefing.md` 수동 붙여넣기)
- [ ] (운영) Approve 후 에디터에 붙여넣기 습관화

### Instagram / Meta

- [ ] 프로페셔널 계정 + Facebook 페이지
- [ ] Meta 앱 + Content Publishing
- [ ] `IG_USER_ID`, long-lived `META_ACCESS_TOKEN`

> 인스타 연동이 준비 중 가장 오래 걸리는 구간입니다.

### Discord (권장 Approve 채널)

- [ ] Developer Portal Bot → `DISCORD_BOT_TOKEN`
- [ ] **텍스트 채널** ID → `DISCORD_CHANNEL_ID` (카테고리 ID 금지) + 봇 초대 (Send / Attach Files / React / History)
- [ ] `NOTIFY_CHANNEL=discord` (또는 자동 선택)
- [ ] `python scripts/smoke_discord.py`

### Telegram

- [ ] BotFather 봇 → `TELEGRAM_BOT_TOKEN`
- [ ] `TELEGRAM_CHAT_ID` + 봇에게 `/start`
- [ ] `python scripts/smoke_telegram.py`

### Postgres / seen_urls

- [x] `docker compose up -d postgres`
- [x] `python scripts/smoke_seen_urls.py`

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
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

./scripts/smoke_ollama.sh
docker compose up -d postgres browserless
MVP_MODE=dry_run python scripts/mvp_pipeline.py
```

### compose 서비스 (기본)

| 서비스 | 역할 | 포트 | 비고 |
|--------|------|------|------|
| `postgres` | DB + `seen_urls` | `5433` | WD_BLACK 데이터 |
| `browserless` | 카드 스크린샷 | `3000` | |
| `n8n` / `ollama` | — | — | 기존 컨테이너 재사용 (`full` 프로필만) |

다음: [07. 워크플로](07-workflow.md)
