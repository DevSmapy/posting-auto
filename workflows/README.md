# n8n 워크플로

## MVP에서의 역할

현재 **실행 가능한 MVP 본체**는 호스트에서 돌리는 Python 파이프라인입니다.

```bash
python scripts/mvp_pipeline.py
```

n8n은 Docker로 함께 띄워 두고, 스케줄·승인 UI·Credentials를 붙이는 오케스트레이터로 확장합니다.

## 권장 연결 (1차)

n8n **Schedule Trigger** → **Execute Command**(또는 SSH)로 호스트 파이프라인 실행:

```bash
cd "/Users/leeyongkyun/포스팅 자동화"
source .venv/bin/activate
MVP_MODE=draft python scripts/mvp_pipeline.py
```

> Execute Command는 n8n 컨테이너 안에서 실행됩니다. 호스트 Python을 쓰려면  
> (a) 파이프라인을 컨테이너에 넣고 의존성 설치, 또는  
> (b) 호스트 cron/`launchd`로 `mvp_pipeline.py`를 돌리고 n8n은 발행·알림만 담당.

## 권장 연결 (2차, 네이티브 노드)

[docs/07-workflow.md](../docs/07-workflow.md)의 노드 표를 n8n UI에서 수동 구성:

1. Schedule  
2. RSS Read ×2 (`GNEWS_*`)  
3. Code (merge / 당일 / cluster)  
4. HTTP Request → Ollama 중요도  
5. HTTP Request → Ollama 브리핑  
6. Telegram Approve  
7. Tistory / Browserless / R2 / Instagram  

`prompts/` 와 `templates/` 는 컨테이너에 `/home/node/prompts`, `/home/node/templates` 로 마운트됩니다.

## 임포트용 스니펫

Code 노드용 샘플은 [`code-nodes/`](code-nodes/)를 참고하세요.
