# n8n 워크플로

## MVP에서의 역할

현재 **실행 가능한 MVP 본체**는 호스트에서 돌리는 Python 파이프라인입니다.

```bash
uv run python scripts/mvp_pipeline.py
```

흐름 요약: RSS → 브리핑 → **카드 PNG** → Discord/Telegram/Slack에서 **이미지 확인 후 Approve** → `briefing.md` (+ 선택 R2/Instagram).

n8n은 Docker로 함께 띄워 두고, 스케줄·Credentials를 붙이는 오케스트레이터로 **후속** 확장합니다.

## 권장 연결 (1차)

n8n **Schedule Trigger** → **Execute Command**(또는 SSH)로 호스트 파이프라인 실행:

```bash
cd "/Users/leeyongkyun/포스팅 자동화"
./scripts/run_draft.sh
# 또는
MVP_MODE=draft uv run python scripts/mvp_pipeline.py
```

> Execute Command는 n8n 컨테이너 안에서 실행됩니다. 호스트 Python을 쓰려면  
> (a) 파이프라인을 컨테이너에 넣고 의존성 설치, 또는  
> (b) 호스트 cron/`launchd`로 `run_draft.sh`를 돌리고 n8n은 알림만 담당.

## 권장 연결 (2차, 네이티브 노드 · 후속)

[docs/07-workflow.md](../docs/07-workflow.md) 참고. 대략:

1. Schedule  
2. RSS Read ×2 (`GNEWS_*`)  
3. Code (merge / 창 필터 / cluster) — 샘플 Code의 “당일” 필터는 Python `since_prev_day_hour`와 다를 수 있음  
4. HTTP Request → Ollama  
5. Notify Approve (또는 Execute Command로 draft 전체)  
6. Browserless / R2 / Instagram (`PUBLISH_CARDS`)  
7. `briefing.md` 경로 알림 (티스토리 Open API 없음)

`prompts/` 와 `templates/` 는 컨테이너에 `/home/node/prompts`, `/home/node/templates` 로 마운트됩니다.

## 임포트용 스니펫

Code 노드용 샘플은 [`code-nodes/`](code-nodes/)를 참고하세요.
