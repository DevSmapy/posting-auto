# 03. 뉴스 수집 (Google News MVP)

## 한 줄 요약

**Google News 한국어 토픽 RSS** (`BUSINESS` + `NATION`) → **전일 15:00~실행시각 창** → (조회수 없음) **피드 순서 + 클러스터 + Ollama 중요도**로 상위 기사 선정.

## MVP 피드 (확정)

```text
https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko
https://news.google.com/rss/headlines/section/topic/NATION?hl=ko&gl=KR&ceid=KR:ko
```

| 토픽 | 용도 |
|------|------|
| `BUSINESS` | 경제·증시·기업·거시 |
| `NATION` | 국내 시사·정치·사회성 이슈 (네이버 “사회”면과 동일하진 않음) |

## 실측 메모 (2026-07-13)

| 소스 | 유효성 | 관찰 |
|------|--------|------|
| 토픽 `BUSINESS` | 높음 | 코스피·반도체·환율 등 브리핑에 적합 |
| 토픽 `NATION` | 중~높음 | 정치·사건·정책 중심 |
| 검색 `경제 when:1d` | 낮음 | 지자체·교육·기고 등 잡음 |
| 검색 `사회 when:1d` | 낮음 | 기관 홍보·로컬 노이즈 |

→ **`경제`/`사회` 키워드 검색 RSS는 MVP에서 사용하지 않음.**

## RSS가 필요한가?

필수는 아닙니다. 다만 Google News는 RSS가 있어 n8n **RSS Read**로 목록을 받기 좋습니다.

## 네이버 섹션 링크와 RSS

- `https://news.naver.com/section/101` (경제), `102` (사회)에는 **공식 RSS가 없음**
- 웹 “RSS 변환기”는 사실상 스크래핑 중개 → DOM 변경·유료·불안정 → **비채택**
- 네이버면 그대로가 필요하면 Phase 2에서 Browserless 스크래핑 + (선택) `#dic_area` 본문

## 날짜 한정 (뉴스 창)

아침 07:30 브리핑이면 **당일 00:00부터**만 보면 전날 장후·저녁 이슈가 빠집니다.

| `NEWS_WINDOW_MODE` | 구간 (Asia/Seoul) |
|--------------------|-------------------|
| `since_prev_day_hour` (기본) | `[전일 NEWS_WINDOW_PREV_DAY_HOUR시, 실행 시각]` — 기본 전일 **15:00** |
| `today` | `[당일 00:00, 실행 시각]` (레거시) |

- 토픽 RSS에 `when:1d`를 붙이는 방식은 불안정할 수 있어 **코드 필터**로 처리
- 창만 넓혀도 LLM에 넣는 상한(`NEWS_LLM_CANDIDATES` / `NEWS_PICK_COUNT`)은 동일

키워드 보강 검색을 나중에 넣을 때만 `q=...+when:1d`를 사용합니다.

## “조회수 순”에 대해

Google News RSS에는 **조회수·트래픽 필드가 없습니다.** 정렬 파라미터도 없습니다.

### 대체 신호 (확정)

1. **구글 피드 노출 순서** — 1차 인기/중요도 프록시  
2. **스토리 클러스터 크기** — `description` HTML 안 관련 기사 `<li>` 개수 (보도량 프록시)  
3. **Ollama 중요도 점수** — 제목 + description(스니펫/관련 묶음) → 1~10점, 상위 선별  

진짜 조회수 랭킹이 필요하면 네이버/다음 랭킹 페이지 스크래핑이 필요하고, 그건 Phase 2 이후입니다.

## 파이프라인 상세

```text
BUSINESS RSS ──┐
               ├─→ merge → 전일15:00~now 창 → dedupe → 신호(순서·클러스터)
NATION RSS  ───┘                                      │
                                                      ▼
                                            Ollama 중요도 (상한 10건대)
                                                      │
                                                      ▼
                                            상위 5건 → 브리핑 생성
```

### LLM에 넘기기 전 하드 게이트

- 뉴스 창 `pubDate` (`NEWS_WINDOW_*`)
- URL·제목 정규화 후 중복 제거
- (선택, 나중) 소스 화이트리스트

### LLM 중요도 (소프트 필터)

스니펫 기반 AI 판정은 기술 필터만으로 “브리핑 가치”를 가르기 어렵기 때문에 **채택**합니다.  
스키마·감점/가점 규칙은 [04. LLM·프롬프트](04-llm-and-prompts.md)를 따릅니다.

## LLM 입력 필드 (기사 단위)

```json
{
  "title": "헤드라인",
  "snippet": "RSS description에서 추출한 텍스트/관련기사 제목들",
  "link": "https://news.google.com/...",
  "source": "한겨레",
  "published_at": "2026-07-13T15:13:00+09:00",
  "topic": "BUSINESS",
  "feed_rank": 3,
  "cluster_size": 5
}
```

## 본문 HTML

MVP에서는 **언론사·네이버 본문 파싱을 하지 않습니다.**  
제목 + 스니펫만으로 요약·카드 카피를 만듭니다.

다음: [04. LLM·프롬프트](04-llm-and-prompts.md)
