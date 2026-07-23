# 외장 드라이브 + 기존 n8n/Ollama 기준 실행 순서

## 스토리지 배치

| 대상 | 드라이브 | 경로 |
|------|----------|------|
| 일반 이미지 tar (n8n, postgres, browserless…) | **WD_BLACK** | `/Volumes/WD_BLACK/Careers/DockerData/images` |
| n8n 데이터 | **WD_BLACK** | `/Volumes/WD_BLACK/Careers/DockerData/n8n_data` |
| postgres 데이터 | **WD_BLACK** | `/Volumes/WD_BLACK/Careers/DockerData/posting-auto/postgres` |
| Ollama 이미지 tar | **Extreme SSD** | `/Volumes/Extreme SSD/DockerData/images` |
| Ollama 모델 데이터 | **Extreme SSD** | `/Volumes/Extreme SSD/DockerData/ollama_data` |

지금 PC에는 이미 아래가 떠 있습니다.

- `n8n` → `:5678` (WD_BLACK `n8n_data`)
- `ollama` → `:11434` (Extreme SSD `ollama_data`)

그래서 **이 프로젝트 Compose로 ollama/n8n을 다시 올리면 포트 충돌**이 납니다.  
MVP는 **기존 컨테이너를 재사용**하고, 부족한 이미지(postgres·browserless)만 WD_BLACK에 skopeo로 받습니다.

관련 환경 변수: `.env` / `.env.example` 의 `IMAGE_DIR`, `OLLAMA_IMAGE_DIR`, `OLLAMA_DATA_PATH`, `POSTGRES_DATA_PATH`, `N8N_DATA_PATH`  
(`Extreme SSD` 경로는 공백 때문에 `.env`에서 **반드시 따옴표**로 감쌉니다.)

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
# 스크립트 하단 ollama 줄 주석 해제 후
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

---

## 3) MVP 파이프라인

```bash
cd "/Users/leeyongkyun/포스팅 자동화"
source .venv/bin/activate

# (권장) Ollama 컨테이너 CPU/메모리 상한 — M2 Air + Desktop ~12GB
# Desktop Settings의 Memory와 컨테이너 --memory는 별개입니다.
chmod +x scripts/limit_ollama_resources.sh
./scripts/limit_ollama_resources.sh   # 기본 4 CPU / 10GB

# 아침 권장: 중요도는 heuristic, 브리핑만 LLM 1회
RANK_MODE=heuristic BRIEFING_MODE=llm MVP_MODE=dry_run python scripts/mvp_pipeline.py
```

결과: `output/<시각>/candidates.json`, `ranked.json`, `briefing.json`  
랭킹이 비면 `importance_raw.json`을 보고, 자동으로 heuristic 폴백이 돕니다.

### draft (Approve → 마크다운)

`.env`에 Discord 또는 Telegram 토큰을 넣고 `NOTIFY_CHANNEL`을 고른 뒤:

```bash
python scripts/smoke_discord.py    # 또는 smoke_telegram.py
python scripts/smoke_seen_urls.py

# 권장: postgres(+browserless) · ollama start → LLM → ollama stop → Discord Approve → aux stop
./scripts/run_draft.sh
# 또는 수동으로 컨테이너를 켠 채:
# MVP_MODE=draft OLLAMA_AUTO_CONTAINER=0 DRAFT_AUTO_AUX=0 python scripts/mvp_pipeline.py
```

토큰 없이 게이트만 검증할 때:

```bash
MVP_MODE=draft NOTIFY_CHANNEL=auto \
  RANK_MODE=heuristic BRIEFING_MODE=heuristic \
  OLLAMA_AUTO_CONTAINER=0 DRAFT_AUTO_AUX=0 \
  python scripts/mvp_pipeline.py
```

단위 체크 (네트워크 없음):

```bash
python scripts/test_notify_window.py
```

### 평일 07:00 cron 예시 (macOS/Linux)

월–금만 (`1-5`). 토·일은 돌리지 않습니다.  
파이프라인은 07:00에 시작하고, Discord Approve 초안은 `.env`의 `NOTIFY_SEND_AT`(기본 07:50)에 보냅니다.

```cron
0 7 * * 1-5 cd "/Users/leeyongkyun/포스팅 자동화" && ./scripts/run_draft.sh >>./output/cron.log 2>&1
```

`./scripts/run_draft.sh` 수명주기:

1. `postgres` (+ `browserless` if `PUBLISH_CARDS`) · `ollama` **start** → 모델 warm (`OLLAMA_WARM_TIMEOUT_SEC` 기본 600초; 실패해도 draft 계속)
2. 랭킹·스토리 건당 LLM
3. **ollama + aux stop** (Discord 발송/Approve 대기 전 — 메모리 반환)
4. Discord Approve 대기 → Approve 시 aux 재기동 → `briefing.md`
5. 종료 시 남은 컨테이너 **stop** (`OLLAMA_AUTO_CONTAINER`/`DRAFT_AUTO_AUX`는 run_draft가 1로 켬)

Docker Desktop은 켜 두세요. 포스팅 목표 시각(예: 08:00)은 수동 붙여넣기 기준이며 코드로 강제하지 않습니다.

| `MVP_MODE` | 동작 |
|------------|------|
| `dry_run` | 수집·LLM만, JSON 저장 |
| `draft` | 초안 → Approve 대기 → `briefing.md` |
| `publish` | Approve 없이 바로 `briefing.md` |

CPU가 여전히 높거나 스토리 요약이 타임아웃되면 `.env`에서:

```bash
OLLAMA_NUM_THREAD=4
OLLAMA_STORY_TIMEOUT_MS=180000
OLLAMA_WARM_TIMEOUT_SEC=600
RANK_MODE=heuristic   # 랭킹만 규칙 기반, 스토리만 건당 LLM
BRIEFING_MODE=llm
# 500/restart 안내가 나면 한 번:
# OLLAMA_DOCKER_RESTART=1 ./scripts/run_draft.sh
```

컨테이너 한도를 Desktop에 맞춘 뒤:

```bash
OLLAMA_DOCKER_MEMORY=10g OLLAMA_DOCKER_CPUS=4 ./scripts/limit_ollama_resources.sh
```

---

## 포트 충돌 요약

| 포트 | 이미 사용 | 이 프로젝트 |
|------|-----------|-------------|
| 11434 | 기존 `ollama` | **다시 띄우지 않음** |
| 5678 | 기존 `n8n` | **다시 띄우지 않음** |
| 5433 | — | `postgres` |
| 3000 | — | `browserless` |

---

## (참고) full 프로필 — 기존 컨테이너 없을 때만

```bash
docker compose --profile full up -d
```

지금처럼 이미 `ollama`/`n8n`이 있으면 **실행하지 마세요.**
