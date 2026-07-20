# 04. LLM · 프롬프트

## Ollama

| 항목 | 값 |
|------|-----|
| 설치 | Docker Compose `ollama` 서비스 (또는 기존 Ollama 컨테이너) |
| 기본 모델 | `qwen2.5:14b` (RAM/CPU 부담 시 `7b`) |
| From n8n | `http://ollama:11434` |
| From 호스트 스크립트 | `http://127.0.0.1:11434` (`OLLAMA_HOST_URL`) |
| API | `POST /api/chat`, `stream: false`, `format: "json"` |
| temperature | `0.2`~`0.4` |
| timeout | `180000` ms (중요도+브리핑 각각 여유) |

모델 pull 예:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:14b
```

### 스모크

```bash
curl http://127.0.0.1:11434/api/tags
./scripts/smoke_ollama.sh
```

## 2단계 LLM 호출

1. **중요도** — heuristic으로 전체 점수 → `HEURISTIC_MIN_SCORE` 이상만 → 기사별 LLM 순차 호출(상한 `NEWS_LLM_CANDIDATES`) → 상위 `NEWS_PICK_COUNT`  
2. **브리핑** — 상위 선정분 → 마크다운/카드용 JSON **1회**

중요도는 후보를 한 프롬프트에 몰아넣지 않고 **기사당 1회**로 나눕니다.

---

## 중요도 점수 JSON (기사 1건)

```json
{
  "id": "article-stable-id",
  "score": 8,
  "audience": "market",
  "reason": "코스피 급락·서킷브레이커, 다수 매체 보도",
  "drop": false
}
```

| 필드 | 설명 |
|------|------|
| `score` | 1~10 |
| `audience` | `market` \| `general` |
| `drop` | 지역 홍보·행사·기고 등이면 `true` |
| `reason` | 짧은 한국어 근거 |

### 선별

- `HEURISTIC_MIN_SCORE` (기본 8): 이 미만은 LLM 미호출
- `NEWS_LLM_CANDIDATES` (기본 10): 임계값 통과분 상한

### 가점

- 시장·금리·환율·실적·규제·대형 사건
- `cluster_size` 큼, `feed_rank` 상위

### 감점 / drop

- 지자체·기관 홍보, 행사 안내, 순수 기고
- 동일 이슈의 가십성 후속
- 브리핑 독자와 무관한 로컬 소식

프롬프트: `prompts/importance_system.md`, `prompts/importance_user.md`

---

## 브리핑 JSON (v2)

```json
{
  "title": "금리, 반도체, AI | 오늘의 경제 브리핑 (2026-07-20)",
  "intro": "도입 2~3문장",
  "core_summary": ["핵심 요약 1", "핵심 요약 2", "핵심 요약 3"],
  "stories": [
    {
      "headline": "재작성 헤드라인",
      "what_happened": "사실을 객관적으로 2~4문장",
      "why_important": "배경·맥락 2~3문장",
      "watch_next": "앞으로 주목할 점 1~2문장",
      "one_liner": "20자 내외",
      "source_name": "한겨레",
      "source_url": "https://..."
    }
  ],
  "market_impact": {
    "positive": ["긍정 영향"],
    "neutral": ["중립 영향"],
    "negative": ["부정 영향"]
  },
  "insight": "이슈들을 연결한 3~5문장",
  "upcoming_events": [
    { "date": "7월 21일", "title": "이벤트명", "description": "한 줄 설명" }
  ],
  "closing_remark": "마무리 한마디",
  "related_keywords": ["금리", "반도체", "AI", "증시", "브리핑"],
  "blog_tags": ["경제", "증시", "브리핑"],
  "slides": [
    { "type": "cover", "headline": "오늘의 경제 브리핑", "body": "2026.07.13" },
    { "type": "story", "headline": "슬라이드 제목", "body": "최대 두 줄" },
    { "type": "disclaimer", "headline": "참고하세요", "body": "투자 판단의 책임은 본인에게 있습니다." }
  ],
  "caption": "인스타 캡션",
  "hashtags": ["경제뉴스", "증시", "주식", "경제브리핑"],
  "sources": [{ "title": "원문 제목", "url": "https://..." }]
}
```

### v1 → v2 필드 대응

| v1 (구) | v2 (신) |
|---------|---------|
| `market_one_liner` | `core_summary` (또는 조립 시 생략) |
| `today_points` | `core_summary` |
| `stories[].summary` | `stories[].what_happened` |
| `stories[].why_it_matters` | `stories[].why_important` |
| — | `stories[].watch_next`, `one_liner` |
| — | `market_impact`, `insight`, `upcoming_events`, `closing_remark`, `related_keywords` |

조립 함수(`assemble_blog_markdown`)는 v1 JSON도 하위 호환으로 렌더링합니다.

### 슬라이드 규칙

- 총 5~7장: `cover` + `story`들 + `disclaimer`
- `body`는 화면 기준 2줄 이내

### 블로그 마크다운 / HTML

LLM이 긴 HTML을 직접 쓰기보다, `intro` / `core_summary` / `stories` / `market_impact` 등을 조립합니다. (로컬 모델 HTML 깨짐 방지)

프롬프트 파일: `prompts/briefing_system.md`, `prompts/briefing_user.md`

---

## 시스템 규칙 (공통)

1. 역할: 한국 경제·시사 브리핑 에디터  
2. 출력: JSON만  
3. 금지: 매수/매도/목표가/수익 보장, 원문 장문 복붙, 출처에 없는 수치 단정  
4. 문체: 쉬운 한국어, 과장 금지  

다음: [05. 발행](05-publishing.md)
