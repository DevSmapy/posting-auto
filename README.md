# 경제 뉴스 자동 포스팅 (n8n + Ollama)

로컬 Docker **n8n + Ollama**로 한국 뉴스를 모아 요약한 뒤, **마크다운 브리핑**(수동 붙여넣기)과 선택적으로 **인스타그램** 카드뉴스를 준비하는 자동화 프로젝트입니다.

> 현재 상태: **반자동** — Telegram Approve → `briefing.md` 저장. 티스토리 Open API는 종료되어 사용하지 않습니다.

---

## 한눈에 보기

| 항목 | 내용 |
|------|------|
| 스케줄 | 평일 07:30 KST (호스트 cron 또는 n8n) |
| 뉴스 소스 (MVP) | Google News KR 토픽 RSS — `BUSINESS` + `NATION` |
| 날짜 | `pubDate` 기준 **당일(Asia/Seoul)** 만 |
| 중요도 | 피드 순서 + 클러스터 크기 + **Ollama 스니펫 점수** |
| LLM | Docker Ollama (`qwen2.5:14b` 권장) |
| 발행 | 마크다운 파일 반자동 (수동 붙여넣기) + 선택적 Instagram |
| 안전장치 | `MVP_MODE=draft` → Telegram Approve/Skip → `briefing.md` |

```text
Google News RSS → 당일/seen_urls 필터 → Ollama 중요도 → Ollama 브리핑
        → (draft) Telegram Approve/Skip → briefing.md (수동 붙여넣기) → seen_urls 기록
```

---

## 지금 실행하기

```bash
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./scripts/smoke_ollama.sh
MVP_MODE=dry_run python scripts/mvp_pipeline.py
```

자세한 단계: [docs/00-mvp-quickstart.md](docs/00-mvp-quickstart.md)

---

## 문서 구조

| 문서 | 내용 |
|------|------|
| [docs/00-mvp-quickstart.md](docs/00-mvp-quickstart.md) | **MVP 실행 가이드** |
| [docs/README.md](docs/README.md) | 문서 목차 |
| [docs/01-overview.md](docs/01-overview.md) | 목표, 산출물, 운영 원칙 |
| [docs/02-architecture.md](docs/02-architecture.md) | 아키텍처, 스택 결정 |
| [docs/03-news-collection.md](docs/03-news-collection.md) | Google News 수집·필터 |
| [docs/04-llm-and-prompts.md](docs/04-llm-and-prompts.md) | Ollama, 중요도·브리핑 JSON |
| [docs/05-publishing.md](docs/05-publishing.md) | 마크다운 반자동, 카드, 인스타, Telegram |
| [docs/06-setup.md](docs/06-setup.md) | 사전 준비, 환경 변수 |
| [docs/07-workflow.md](docs/07-workflow.md) | n8n 노드 흐름 |
| [docs/08-roadmap.md](docs/08-roadmap.md) | 로드맵, 트러블슈팅, 보안 |

---

## 디렉터리

```text
포스팅 자동화/
├── README.md
├── docs/
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── prompts/
├── templates/cards/
├── scripts/
│   ├── smoke_ollama.sh
│   └── mvp_pipeline.py      # MVP 실행 진입점
├── workflows/
└── init/01_seen_urls.sql
```

---

## 핵심 결정 (요약)

1. **뉴스**: Google News 토픽 RSS. 네이버 섹션·키워드 검색 RSS는 MVP 제외.
2. **조회수 정렬 불가** → 구글 노출 순서 + 클러스터 + Ollama 중요도.
3. **본문 HTML 파싱 안 함** (MVP) → RSS 제목·스니펫만으로 요약.
4. **LLM = Ollama (Docker Compose)**.
5. **발행 전** `draft`로 Telegram 확인 권장.

---

## 면책

생성·발행 콘텐츠는 정보 안내용이며 투자 권유가 아닙니다. 법적·투자 책임은 운영자에게 있습니다.
