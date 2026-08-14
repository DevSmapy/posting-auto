# MVP 빠른 시작 (실행 · 설치)

외장 드라이브 + 기존 n8n/Ollama 기준 실행 순서와 사전 설정 체크리스트입니다.

## 사전 준비 체크리스트

### 공통

- [ ] Docker Desktop
- [ ] 여유 RAM: `14b` 기준 16GB+ 권장 (`7b`는 더 낮아도 가능)

### Ollama (Docker)

**A) Compose가 ollama를 소유할 때** (`--profile full`, 기존 컨테이너 없을 때만):

- [ ] `docker compose --profile full up -d ollama`
- [ ] `curl -fsS --retry 15 --retry-delay 1 --retry-all-errors --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null`
- [ ] `docker compose exec ollama ollama pull qwen2.5:14b`
- [ ] `./scripts/smoke_ollama.sh` (호스트 → `127.0.0.1:11434`)

**B) 외장 Ollama 재사용** (기본 MVP — Compose로 start/exec 하지 않음):

- [ ] `:11434` 응답 확인 (`curl http://127.0.0.1:11434/api/tags`)
- [ ] 모델 없으면: `curl -N http://127.0.0.1:11434/api/pull -d '{"name":"qwen2.5:14b"}'`
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

## 환경 변수 · 스토리지

전체 목록은 [`.env.example`](../.env.example)을 보세요. (`cp .env.example .env`)

| 대상 | 드라이브 | 경로 |
|------|----------|------|
| 일반 이미지 tar (n8n, postgres, browserless…) | **WD_BLACK** | `/Volumes/WD_BLACK/Careers/DockerData/images` |
| n8n 데이터 | **WD_BLACK** | `/Volumes/WD_BLACK/Careers/DockerData/n8n_data` |
| postgres 데이터 | **WD_BLACK** | `/Volumes/WD_BLACK/Careers/DockerData/posting-auto/postgres` |
| Ollama 이미지 tar | **Extreme SSD** | `/Volumes/Extreme SSD/DockerData/images` |
| Ollama 모델 데이터 | **Extreme SSD** | `/Volumes/Extreme SSD/DockerData/ollama_data` |

| 변수 | 기본 경로 |
|------|-----------|
| `IMAGE_DIR` | `/Volumes/WD_BLACK/Careers/DockerData/images` |
| `POSTGRES_DATA_PATH` | `/Volumes/WD_BLACK/Careers/DockerData/posting-auto/postgres` |
| `N8N_DATA_PATH` | `/Volumes/WD_BLACK/Careers/DockerData/n8n_data` |
| `OLLAMA_IMAGE_DIR` | `"/Volumes/Extreme SSD/DockerData/images"` (따옴표 필수) |
| `OLLAMA_DATA_PATH` | `"/Volumes/Extreme SSD/DockerData/ollama_data"` (따옴표 필수) |

### 경로 A — 기존 컨테이너 재사용 (이 PC 기본)

이미 아래가 떠 있으면 Compose로 ollama/n8n을 **다시 올리지 마세요** (포트 충돌).

- `n8n` → 포트 **5678** (WD_BLACK `n8n_data`)
- `ollama` → 포트 **11434** (Extreme SSD `ollama_data`)

모델 pull·스모크는 Compose exec 없이 호스트에서:

```bash
curl http://127.0.0.1:11434/api/tags
curl -N http://127.0.0.1:11434/api/pull -d '{"name":"qwen2.5:14b"}'   # 없을 때만
./scripts/smoke_ollama.sh
```

MVP는 이 경로로 **기존 컨테이너를 재사용**하고, 부족한 이미지(postgres·browserless)만 WD_BLACK에 skopeo로 받습니다.

### 경로 B — Compose가 ollama를 소유 (`--profile full`)

기존 `ollama`/`n8n`이 **없을 때만**. pull은 `docker compose exec ollama …`를 씁니다. 아래 “(참고) full 프로필” 참고.

> `Extreme SSD`처럼 경로에 공백이 있으면 `.env`에서 **반드시 `"..."`로 감싸야** 합니다.  
> 따옴표 없이 `source .env` 하면 `/Volumes/Extreme` 까지만 변수에 들어가고 깨집니다.

Ollama API: 컨테이너용 `OLLAMA_BASE_URL=http://host.docker.internal:11434`,  
호스트 스크립트용 `OLLAMA_HOST_URL=http://127.0.0.1:11434`.  
`.env`는 git에 올리지 않습니다.

의존성·가상환경은 **uv** 기준입니다 (`pyproject.toml`).  
(`requirements.txt`는 호환용 미러이며, 신규 설치는 `uv sync`를 쓰세요.)

---

## 0) (선택) 잘못 pull 한 이미지 정리

```bash
docker images
docker rmi postgres:16-alpine ghcr.io/browserless/chromium:latest 2>/dev/null || true
# ollama/n8n 이미지는 기존 컨테이너가 쓰면 지우지 마세요.
```

`posting-auto` 쪽 ollama가 떠 있었다면:

```bash
docker compose -f "/Users/leeyongkyun/포스팅 자동화/docker-compose.yml" --profile full down
docker rm -f posting-auto-ollama-1 2>/dev/null || true
```

---

## 1) 이미지 받기 (skopeo → WD_BLACK)

```bash
cd "/Users/leeyongkyun/포스팅 자동화"
chmod +x scripts/skopeo_pull_images.sh
./scripts/skopeo_pull_images.sh
# 기본 IMAGE_DIR = /Volumes/WD_BLACK/Careers/DockerData/images
```

Ollama 이미지 tar만 Extreme SSD에 둘 때(선택):

```bash
IMAGE_DIR="$OLLAMA_IMAGE_DIR" ./scripts/skopeo_pull_images.sh
# 또는
IMAGE_DIR="/Volumes/Extreme SSD/DockerData/images" ./scripts/skopeo_pull_images.sh
```

> Mac에서 `skopeo → docker-daemon` 은 `closed pipe` 오류가 납니다.  
> 스크립트는 **skopeo tar → `docker load`** + `linux/arm64` override 를 사용합니다.

---

## 2) 보조 컨테이너만 기동 (ollama/n8n 제외)

```bash
cd "/Users/leeyongkyun/포스팅 자동화"
mkdir -p "/Volumes/WD_BLACK/Careers/DockerData/posting-auto/postgres"

docker compose up -d postgres browserless
docker compose ps
./scripts/smoke_ollama.sh
```

| 서비스 | 역할 | 포트 | 비고 |
|--------|------|------|------|
| `postgres` | DB + `seen_urls` | `5433` | WD_BLACK 데이터 |
| `browserless` | 카드 스크린샷 | `3000` | |
| `n8n` / `ollama` | — | — | 기존 컨테이너 재사용 (`full` 프로필만) |

---

## 3) MVP 파이프라인

```bash
cd "/Users/leeyongkyun/포스팅 자동화"
uv sync   # 최초 1회 또는 의존성 변경 시

# (권장) Ollama 컨테이너 CPU/메모리 상한 — M2 Air + Desktop ~12GB
chmod +x scripts/limit_ollama_resources.sh
./scripts/limit_ollama_resources.sh   # 기본 4 CPU / 10GB

# 아침 권장: 중요도는 heuristic, 브리핑만 LLM 1회
RANK_MODE=heuristic BRIEFING_MODE=llm MVP_MODE=dry_run \
  uv run python scripts/mvp_pipeline.py
```

결과: `output/<시각>/candidates.json`, `ranked.json`, `briefing.json`  
랭킹이 비면 `importance_raw.json`을 보고, 자동으로 heuristic 폴백이 돕니다.

### draft (2단계 게이트 → 마크다운)

`.env`에 Discord, Telegram, 또는 Slack 토큰을 넣고 `NOTIFY_CHANNEL`을 고른 뒤:

```bash
uv run python scripts/smoke_discord.py    # 또는 smoke_telegram.py / smoke_slack.py
uv run python scripts/smoke_seen_urls.py

# 권장: content gate → render gate → cleanup ask
./scripts/run_draft.sh
```

로컬 트래킹 예: `git fetch origin && git checkout -t origin/<feature-branch>`  
① 내용(✅/🔀/✍️) → ② 이미지(✅/🔁) → ③ cleanup. 재시도: `CONTENT_RETRY_MAX` / `RENDER_RETRY_MAX`.  
게이트·parked resume 상세: [04. 발행·워크플로](04-publishing.md).

토큰 없이 게이트만 검증할 때:

```bash
MVP_MODE=draft NOTIFY_CHANNEL=auto \
  RANK_MODE=heuristic BRIEFING_MODE=heuristic \
  OLLAMA_AUTO_CONTAINER=0 DRAFT_AUTO_AUX=0 \
  uv run python scripts/mvp_pipeline.py
```

단위 체크 (네트워크 없음):

```bash
uv run python scripts/test_notify_window.py
uv run python -m unittest discover -s tests -v
```

### 카드뉴스 로컬 미리보기 (Ollama / R2 / IG 불필요)

```bash
docker compose up -d browserless   # PNG용 (선택; Chrome만 있어도 됨)
uv run python scripts/preview_cardnews.py
# → output/cardnews-preview/
```

슬라이드·인스타 본문·발행: [04. 발행·워크플로](04-publishing.md).  
템플릿 구조·에디토리얼 UI: [05. 카드 템플릿](05-card-templates.md).  
Template Studio: `uv run streamlit run apps/template_studio/app.py`

### 평일 cron + Ops Console (macOS/Linux)

```bash
cp config/ops.example.json config/ops.json
uv sync
uv run streamlit run apps/ops_console/app.py
```

`config/ops.json`의 `schedule.run_at` / `notify_at` / `feeds` / `cards.bundle_id`를 저장하면 파이프라인·cron이 읽습니다.  
`NOTIFY_SEND_AT`·`CARD_BUNDLE_ID`·`GNEWS_*` env가 있으면 해당 항목만 env가 우선합니다.

```cron
0 6 * * 1-5 "/ABSOLUTE/PATH/TO/REPO/scripts/cron_run_draft.sh" >>"/ABSOLUTE/PATH/TO/REPO/output/cron.log" 2>&1
```

`cron_run_draft.sh`는 `MVP_MODE=autonomous AUTO_PUBLISH=false` (Wave 1)만 돌린다. 예전 draft Approve 아침 경로는 타지 않는다.

`./scripts/run_draft.sh` 수명주기:

1. `ollama` **start** → 모델 warm (기본 600초; 실패해도 draft 계속)
2. 랭킹·스토리 건당 LLM (① 내용 게이트 동안 Rerank/Rewrite 시 **ollama 유지**)
3. 내용 **Approve** 후 **ollama stop**
4. `postgres` (+ `browserless` if cards) **start** → 카드 렌더
5. 렌더 종료 후 aux **stop** → publish 직전 aux **재기동** → publish → 종료 시 stop

| `MVP_MODE` | 동작 |
|------------|------|
| `dry_run` | 수집·LLM만, JSON 저장 |
| `draft` | 내용 게이트 → 렌더 게이트 Approve 후 `briefing.md` |
| `publish` | 채널 Approve **우회**, 바로 `briefing.md` |

CPU가 높거나 스토리 타임아웃이면 `.env`에서:

```bash
OLLAMA_NUM_THREAD=4
OLLAMA_NUM_CTX=4096
OLLAMA_STORY_TIMEOUT_MS=300000
OLLAMA_LOAD_TIMEOUT=10m
OLLAMA_WARM_TIMEOUT_SEC=600
RANK_MODE=heuristic
BRIEFING_MODE=llm
```

```bash
OLLAMA_DOCKER_MEMORY=10g OLLAMA_DOCKER_CPUS=4 ./scripts/limit_ollama_resources.sh
```

---

## 포트 충돌 요약

| 포트 | 경로 A (재사용) | 경로 B (`--profile full`) |
|------|-----------------|---------------------------|
| 11434 | 기존 `ollama` | Compose `ollama` |
| 5678 | 기존 `n8n` | Compose `n8n` |
| 5433 | Compose `postgres` | Compose `postgres` |
| 3000 | Compose `browserless` | Compose `browserless` |

---

## (참고) full 프로필 — 경로 B, 기존 컨테이너 없을 때만

```bash
docker compose --profile full up -d
curl -fsS --retry 15 --retry-delay 1 --retry-all-errors --max-time 2 \
  http://127.0.0.1:11434/api/tags >/dev/null
docker compose exec ollama ollama pull qwen2.5:14b
./scripts/smoke_ollama.sh
```

경로 A처럼 이미 `ollama`/`n8n`이 있으면 **실행하지 마세요.**

다음: [01. 개요·아키텍처](01-overview.md)
