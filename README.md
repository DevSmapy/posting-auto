# 경제 뉴스 자동 포스팅 (n8n + Ollama)

로컬 Docker **n8n + Ollama**로 한국 뉴스를 모아 요약한 뒤, **마크다운 브리핑**(수동 붙여넣기)과 선택적으로 **인스타그램** 카드뉴스를 준비하는 자동화 프로젝트입니다.

> 현재 상태: **반자동** — Discord/Telegram/Slack Approve → `briefing.md` 저장. 티스토리 Open API는 종료되어 사용하지 않습니다.

운영자(사람)가 목표·범위·검수를 담당하고, AI·바이브코딩은 구현·문서·테스트 **도구**로 사용합니다. 역할 구분: [docs/01-overview.md](docs/01-overview.md).

---

## 한눈에 보기

| 항목 | 내용 |
|------|------|
| 스케줄 | 평일 06:00 Wave 1 (`autonomous`, 인스타 실게시 없음) → 08:00 전 패키지 (cron `1-5`) |
| 뉴스 소스 (MVP) | Google News KR 토픽 RSS — `BUSINESS` + `NATION` |
| 날짜 | `pubDate` ∈ **전일 15:00 ~ 실행시각** (Asia/Seoul) |
| 중요도 | 피드 순서 + 클러스터 + **Ollama 스니펫 점수** |
| LLM | Docker Ollama (`qwen2.5:14b` 권장), layered story |
| 발행 | 마크다운 반자동 + 선택적 Instagram (`publish_ready`) |
| 안전장치 | `MVP_MODE=draft` → 내용/렌더 게이트 → Approve → `briefing.md` |

---

## 지금 실행하기

```bash
cp .env.example .env
uv sync
./scripts/smoke_ollama.sh
MVP_MODE=dry_run uv run python scripts/mvp_pipeline.py
```

자세한 단계: [docs/00-mvp-quickstart.md](docs/00-mvp-quickstart.md)

---

## 문서 구조

| 문서 | 내용 |
|------|------|
| [docs/00-mvp-quickstart.md](docs/00-mvp-quickstart.md) | **실행·설치** |
| [docs/README.md](docs/README.md) | 문서 목차 |
| [docs/01-overview.md](docs/01-overview.md) | 개요·아키텍처·사람/AI 역할 |
| [docs/02-news-collection.md](docs/02-news-collection.md) | Google News 수집·필터 |
| [docs/03-llm-and-prompts.md](docs/03-llm-and-prompts.md) | Ollama·브리핑 JSON |
| [docs/04-publishing.md](docs/04-publishing.md) | 게이트·발행·publish_ready |
| [docs/05-card-templates.md](docs/05-card-templates.md) | 카드 HTML·번들·editorial |
| [docs/06-roadmap.md](docs/06-roadmap.md) | 로드맵·트러블슈팅·보안 |
| [docs/07-pr-conventions.md](docs/07-pr-conventions.md) | PR Summary / Changes / Notes |

---

## 디렉터리

```text
포스팅 자동화/
├── README.md
├── docs/
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── prompts/
├── templates/cards/
├── apps/                  # ops_console, template_studio
├── scripts/
│   ├── mvp_pipeline.py
│   ├── cards/
│   └── publish/
├── workflows/
└── init/01_seen_urls.sql
```

---

## 면책

생성·발행 콘텐츠는 정보 안내용이며 투자 권유가 아닙니다. 법적·투자 책임은 운영자에게 있습니다.
