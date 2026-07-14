# 02. 아키텍처

## 파이프라인

```text
[Cron 07:30 KST]
       │
       ▼
[Google News RSS: BUSINESS + NATION]
       │
       ▼
[당일 pubDate 필터] → [URL/제목 중복 제거] → [피드순서·클러스터 신호]
       │
       ▼
[Ollama 중요도 점수] → 상위 후보
       │
       ▼
[Ollama 브리핑 JSON]
       │
       ▼
[Telegram 초안] Approve / Skip
       │
       ├─ Skip → 종료
       │
       └─ Approve
            ├─▶ briefing.md (수동 붙여넣기)
            └─▶ 카드 HTML → Browserless PNG → R2 → Instagram Carousel
                    │
                    ▼
              Telegram 결과 알림
```

## 프로세스 구성

| 구성요소 | 실행 위치 | 역할 |
|----------|-----------|------|
| n8n | Docker | 스케줄, HTTP/RSS, 분기, 알림 |
| Postgres | Docker | n8n 메타 + `seen_urls` |
| Browserless | Docker | 카드 HTML → 1080×1080 PNG |
| Ollama | **Docker Compose** (`ollama` 서비스) | 중요도·브리핑 |
| Cloudflare R2 | 클라우드 | 인스타용 공개 이미지 URL |

같은 Compose 네트워크에서 n8n → `http://ollama:11434` 로 호출합니다.  
호스트에서 `scripts/mvp_pipeline.py`를 돌릴 때는 포트 포워드된 `http://127.0.0.1:11434` (`OLLAMA_HOST_URL`)를 씁니다.

이미 **다른 Compose/컨테이너로 Ollama만 따로** 띄워 두었다면, 이 프로젝트의 `ollama` 서비스는 끄고 `.env`의 `OLLAMA_BASE_URL`만 기존 컨테이너에 맞게 맞추면 됩니다 (포트 `11434` 충돌 주의).

## 기술 스택과 설계 결정

| 영역 | 선택 | 이유 |
|------|------|------|
| 오케스트레이션 | n8n self-host | 로컬 Docker, 포스팅 파이프라인에 적합 |
| 뉴스 목록 | Google News KR 토픽 RSS | 키 없이 RSS 사용 가능, n8n 연동 단순 |
| LLM | Ollama (Docker) | 비용·프라이버시, n8n과 같은 Compose |
| LLM 비채택 | LM Studio | 실험용. 스케줄 headless에는 Ollama |
| 블로그 | 마크다운 반자동 | Open API 종료 → 수동 붙여넣기 |
| 카드 채널 | Instagram Graph API | 비즈니스/크리에이터 + 페이지 |
| 카드 이미지 | HTML + Browserless | 한글 타이포·레이아웃 통제 |
| 이미지 호스팅 | Cloudflare R2 | 인스타 Media API는 공개 HTTPS URL 필요 |
| 승인 | Telegram Bot | 금융 콘텐츠 품질 게이트 |

## 의도적으로 미룬 것 (Phase 2+)

- 네이버 뉴스 섹션(`101`/`102`) 스크래핑
- 언론사·네이버 기사 본문 HTML 파싱
- 실제 조회수/랭킹 페이지 기반 정렬
- 클라우드 LLM 폴백

다음: [03. 뉴스 수집](03-news-collection.md)
