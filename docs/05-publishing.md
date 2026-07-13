# 05. 발행 (티스토리 · 카드 · 인스타 · Telegram)

## Telegram 승인 게이트

### 미리보기에 포함

- 제목, 시장 한줄
- 선정 뉴스 헤드라인 + 중요도 점수
- 카드 슬라이드 headline 목록
- **Approve / Skip**

| 선택 | 동작 |
|------|------|
| Approve | 티스토리 + 카드/인스타 진행 |
| Skip | 종료. 기본: `seen_urls` 미기록 (다음날 다시 후보 가능) |

Approve 후 **발행 성공 시**에만 `seen_urls`에 insert.

---

## 티스토리

- 문서: [티스토리 Open API](https://www.tistory.com/guide/api/manage/register)
- `POST` `https://www.tistory.com/apis/post/write`

| 파라미터 | 값 |
|----------|-----|
| `access_token` | `.env` |
| `blogName` | `.env` |
| `title` | 브리핑 `title` |
| `content` | 조립 HTML |
| `visibility` | `3` 테스트 → `0` 운영 |
| `tag` | `blog_tags` |

테스트 순서: 수동 비공개 → n8n 비공개 → 공개.

---

## 카드뉴스 렌더

템플릿(예정):

- `templates/cards/cover.html`
- `templates/cards/slide.html`
- `templates/cards/disclaimer.html`

공통: 1080×1080, 큰 제목 + 짧은 본문, 브랜드/블로그명 푸터.

1. 슬라이드별 HTML 주입  
2. Browserless screenshot → PNG  
3. R2(S3 호환) 업로드 → 공개 URL  

인스타 Graph API는 **이미지 URL**이 필요하므로 R2(또는 S3)를 MVP 기본으로 둡니다.

---

## Instagram 캐러셀

전제: 프로페셔널 계정 + Facebook 페이지 + Meta 앱 Content Publishing.

1. 이미지마다 `POST /{IG_USER_ID}/media` (`is_carousel_item=true`)  
2. 부모 `media_type=CAROUSEL` + `children` + `caption`  
3. 상태 `FINISHED` 폴링  
4. `POST /{IG_USER_ID}/media_publish`  

버전: `.env`의 `META_GRAPH_VERSION` (예: `v21.0`).

---

## 면책 문구 (고정)

> 본 콘텐츠는 정보 안내용이며 특정 종목의 매수·매도·투자를 권유하지 않습니다. 투자 판단과 책임은 독자 본인에게 있습니다.

블로그 하단·카드 마지막 슬라이드·인스타 캡션 중 최소 한 곳에 포함합니다.

다음: [06. 설치·설정](06-setup.md)
