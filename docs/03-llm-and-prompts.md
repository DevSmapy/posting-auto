# 03. LLM · 프롬프트

## Ollama

| 항목 | 값 |
|------|-----|
| 설치 | Docker Compose `ollama` 서비스 (또는 기존 Ollama 컨테이너) |
| 기본 모델 | `qwen2.5:14b` (RAM/CPU 부담 시 `7b`) |
| From n8n | `http://ollama:11434` |
| From 호스트 스크립트 | `http://127.0.0.1:11434` (`OLLAMA_HOST_URL`) |
| API | `POST /api/chat`, `stream: false`, `format: "json"` |
| temperature | `0.2`~`0.4` |
| timeout | 건당 스토리: `.env.example` 권장 `300000` ms (`OLLAMA_STORY_TIMEOUT_MS`); 미설정 시 폴백 `120000` ms |

모델 pull 예:

```bash
# Compose 소유 경로 (--profile full, 기존 ollama 없을 때만)
docker compose --profile full up -d ollama
docker compose exec ollama ollama pull qwen2.5:14b

# 외장 컨테이너 재사용 (Compose start/exec 없음)
curl -N http://127.0.0.1:11434/api/pull -d '{"name":"qwen2.5:14b"}'
```

### 스모크

```bash
curl http://127.0.0.1:11434/api/tags
./scripts/smoke_ollama.sh
```

## LLM 호출 구조

1. **중요도 (선택)** — 아침 기본은 `RANK_MODE=heuristic`. `RANK_MODE=llm`일 때만 heuristic 필터 후 기사별 중요도 LLM  
2. **스토리 생성** — 선정 기사 **건당** layered story generation
   - Fact layer (`story_fact_system` / `story_fact_user`)
   - Translation layer (`story_translate_system` / `story_translate_user`)
   - Polish/validator layer (`story_polish_*` + `scripts/story_quality.py`)
3. **Envelope 조립** — 코드는 story fields에서 title/intro/core_summary/slides/caption 등을 rule-based 조립

전체 브리핑 JSON을 한 번에 생성하는 경로(구 `briefing_*.md`)는 사용하지 않습니다. 타임아웃·품질 붕괴의 원인이었습니다.

건당 타임아웃: `OLLAMA_STORY_TIMEOUT_MS` → `OLLAMA_BRIEFING_TIMEOUT_MS` → `OLLAMA_TIMEOUT_MS` → **120000**

서버 로드 한도: 컨테이너 `OLLAMA_LOAD_TIMEOUT` (기본 10m; `run_draft`가 미설정 시 재생성).  
warm은 스토리와 **같은 `options`(num_ctx/num_thread)** 로 호출해 runner 재로드를 막습니다.

생성 모드 로그: `llm` (전원 성공) | `mixed` (일부 폴백) | `heuristic` (전부 폴백 또는 `BRIEFING_MODE=heuristic`)

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

## Story layer (건당) → envelope 취합

최종 downstream contract는 유지합니다. `source_name` / `source_url`은 코드를 통해 원문에서 채웁니다.

```json
{
  "headline": "짧은 재작성 제목",
  "what_happened": "2~4문장",
  "why_important": "2~3문장",
  "watch_next": "1~2문장",
  "one_liner": "완결 한 문장"
}
```

### 내부 3-layer 구조

#### 1) Fact layer

기사 1건에서 스타일 이전의 구조화 사실만 추출합니다. 기본 intermediate는 source-neutral/영어 중심 짧은 문장 JSON입니다.

예:

```json
{
  "headline_hint": "Rate pause",
  "event": "Inflation eased.",
  "cause": "Expectations shifted.",
  "impact": "Markets repriced policy.",
  "watch_next": "Watch the Fed.",
  "one_liner_hint": "Inflation eased and rate expectations moved.",
  "entities": ["Fed"],
  "tone_flags": ["macro"]
}
```

#### 2) Translation layer

Fact layer 결과를 `TARGET_LANGUAGE` / `TARGET_LOCALE` 기준의 story JSON 초안으로 변환합니다.

- **요청 받은 대상 언어만 출력**
- 고유명사·티커·필수 약어 외 다른 언어 잔존 금지
- 의미 변경 금지

#### 3) Polish layer

기본은 비-LLM validator + deterministic trim/repair 입니다.  
`scripts/story_quality.py`가 다음을 점검합니다.

- target-language ratio / disallowed-language ratio
- duplicate fields (`headline == one_liner` 등)
- 길이/fit 검사
- `one_liner` 품질 검사

validator 실패 시에만 좁은 범위 LLM rewrite를 1회 시도합니다. 이후에도 실패하면 **story 단위 heuristic fallback**으로 내려갑니다.

### Envelope 조립

코드 `assemble_briefing_from_stories`가 최종 브리핑 envelope를 만듭니다:

```json
{
  "title": "오늘 주요 경제·시장 이슈를 정리합니다 | 오늘의 경제 브리핑 (YYYY-MM-DD)",
  "intro": "도입 2~3문장",
  "core_summary": ["스토리 one_liner …"],
  "stories": [
    {
      "headline": "재작성 헤드라인",
      "what_happened": "사실을 객관적으로 2~4문장",
      "why_important": "배경·맥락 2~3문장",
      "watch_next": "앞으로 주목할 점 1~2문장",
      "one_liner": "이슈 핵심을 담은 완결 한 문장",
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
  "blog_tags": ["경제", "브리핑"],
  "slides": [
    { "type": "cover", "headline": "오늘의 경제 브리핑", "body": "2026.07.13" },
    { "type": "story", "headline": "슬라이드 제목", "body": "최대 두 줄" },
    { "type": "disclaimer", "headline": "참고하세요", "body": "투자 판단의 책임은 본인에게 있습니다." }
  ],
  "caption": "인스타 캡션",
  "hashtags": ["경제뉴스", "증시", "주식", "경제브리핑"]
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

### 슬라이드 · 인스타 본문 규칙

코드 `scripts/cards` (`CardAssembler`, `InstagramCaptionBuilder`)가 stories에서 조립합니다.

- **Upstream 계약:** 파이프라인은 stories **3~5개**를 넘기는 것을 전제로 함 (`NEWS_PICK_COUNT` 기본 5). `CardAssembler`는 6개 이상이면 앞 5개로 clamp
- **최종 슬라이드:** `cover` 1 + `story` N + `disclaimer` 1 → N이 3~5이면 항상 **5~7장** (N이 3 미만인 thin-day는 5장 미만 가능)
- story `body`는 **`one_liner` 우선**, 화면 기준 2줄 이내
- `caption` / `hashtags` / `instagram_post`: 훅 + 오늘의 포인트 + CTA + 면책 + 해시태그 (≤2100자). `hashtags`는 `full_text`에 남은 태그와 일치
- LLM에 긴 캡션·HTML을 맡기지 않음 (블로그 조립과 동일 원칙)

### 블로그 마크다운 / HTML

`intro` / `core_summary` / `stories` / `market_impact` 등을 코드가 조립합니다. (로컬 모델 HTML 깨짐 방지)

프롬프트 파일:

- `prompts/story_fact_system.md`, `prompts/story_fact_user.md`
- `prompts/story_translate_system.md`, `prompts/story_translate_user.md`
- `prompts/story_polish_system.md`, `prompts/story_polish_user.md`

레거시 하위 호환:

- `prompts/story_system.md`, `prompts/story_user.md`
- `prompts/briefing_system.md`, `prompts/briefing_user.md` (미사용)

---

## 시스템 규칙 (공통)

1. 역할: 경제·시사 브리핑 생성기 (fact / translation / polish로 분리)  
2. 출력: JSON만  
3. 금지: 매수/매도/목표가/수익 보장, 원문 장문 복붙, 출처에 없는 수치 단정  
4. 문체: 대상 언어의 일반 독자가 이해할 수 있는 자연스러운 표현, 과장 금지  

다음: [04. 발행·워크플로](04-publishing.md)
