# 문서 목차

이 폴더는 프로젝트의 **상세 설계·운영 문서**입니다. 요약은 루트 [README.md](../README.md)를 보세요.

Python 의존성·실행은 **uv** 기준입니다 (`uv sync`, `uv run python …`).

| 순서 | 문서 | 설명 |
|------|------|------|
| 00 | [MVP 빠른 시작](00-mvp-quickstart.md) | **실행·설치 (여기부터)** |
| 01 | [개요·아키텍처](01-overview.md) | 목표, 사람/AI 역할, 파이프라인, 스택 |
| 02 | [뉴스 수집](02-news-collection.md) | Google News MVP, 날짜·중요도 |
| 03 | [LLM·프롬프트](03-llm-and-prompts.md) | Ollama, layered story, JSON 계약 |
| 04 | [발행·워크플로](04-publishing.md) | 2단계 게이트, publish_ready, seen_urls |
| 05 | [카드 템플릿](05-card-templates.md) | 루트 HTML vs editorial, 번들 |
| 06 | [로드맵·운영](06-roadmap.md) | 구현 순서, MVP, 트러블슈팅, 보안 |
| 07 | [PR 관례](07-pr-conventions.md) | Summary / Changes / Notes |

```text
docs/
├── README.md
├── 00-mvp-quickstart.md
├── 01-overview.md
├── 02-news-collection.md
├── 03-llm-and-prompts.md
├── 04-publishing.md
├── 05-card-templates.md
├── 06-roadmap.md
└── 07-pr-conventions.md
```
