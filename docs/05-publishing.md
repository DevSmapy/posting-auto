# 05. 발행 (반자동 마크다운 · 카드 · 인스타 · Telegram)

> 티스토리 Open API는 2024년 종료되었습니다. 블로그 발행은 **마크다운 파일 수동 붙여넣기**로 합니다.

## Telegram 승인 게이트

`MVP_MODE=draft` 일 때 [`scripts/mvp_pipeline.py`](../scripts/mvp_pipeline.py)가 초안을 보낸 뒤 **Approve/Skip**을 기다립니다.

### 미리보기에 포함

- 제목, 시장 한줄
- 선정 뉴스 헤드라인 + 중요도 점수
- 카드 슬라이드 headline 목록
- **Approve / Skip** (인라인 버튼) 또는 `/approve` `/skip` 텍스트

| 선택 | 동작 |
|------|------|
| Approve | `output/<시각>/briefing.md` 저장 (+ Telegram에 경로·미리보기) |
| Skip | 종료. `seen_urls` 미기록 |
| 타임아웃 | `TELEGRAM_APPROVE_TIMEOUT_SEC`(기본 900초) 후 Skip과 동일 |

| `TELEGRAM_APPROVE_MODE` | 동작 |
|-------------------------|------|
| (미설정) | 토큰 있으면 `telegram`, 없으면 `cli` |
| `telegram` | 인라인 버튼 + `getUpdates` 폴링 |
| `cli` | 터미널에 `approve` / `skip` 입력 |
| `auto` | 대기 없이 승인 (로컬 스모크) |

Approve 후 **마크다운 저장 성공 시**에만 `seen_urls`에 insert.

스모크: `python scripts/smoke_telegram.py`

---

## 반자동 블로그 (Markdown)

산출물:

| 파일 | 용도 |
|------|------|
| `briefing.md` | 에디터에 붙여넣기 (권장) |
| `briefing.html` | HTML이 필요할 때 |
| `briefing.json` | LLM 원본 구조 |

티스토리/다른 블로그 글쓰기 화면에 `briefing.md` 내용을 복사해 붙이면 됩니다.

---

## 카드뉴스 / Instagram (옵션)

`PUBLISH_CARDS=1` 일 때만 Approve 후 카드 렌더·R2·인스타를 시도합니다. 기본은 `0`(마크다운만).

템플릿:

- `templates/cards/cover.html`
- `templates/cards/slide.html`
- `templates/cards/disclaimer.html`

1. 슬라이드별 HTML 주입  
2. Browserless screenshot → PNG  
3. R2 업로드 → Instagram Graph API 캐러셀  

---

## 면책 문구 (고정)

> 본 콘텐츠는 정보 안내용이며 특정 종목의 매수·매도·투자를 권유하지 않습니다. 투자 판단과 책임은 독자 본인에게 있습니다.

다음: [06. 설치·설정](06-setup.md)
