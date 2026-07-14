# 08. 로드맵 · MVP · 트러블슈팅 · 보안

## 구현 로드맵

| 단계 | 작업 | 완료 기준 |
|------|------|-----------|
| 0 | 문서 체계 (README + `docs/`) | 본 문서 트리 존재 |
| 1 | `docker-compose` + `.env.example` + `.gitignore` | 파일 존재, `docker compose up` 가능 |
| 2 | Ollama 스모크 스크립트 | `./scripts/smoke_ollama.sh` |
| 3 | `prompts/` + `templates/cards/` | 샘플 템플릿·프롬프트 존재 |
| 4 | MVP 파이프라인 (RSS→중요도→브리핑) | `MVP_MODE=dry_run python scripts/mvp_pipeline.py` |
| 5 | Telegram draft / 티스토리 publish 경로 | `.env` 토큰 후 `draft`·`publish` (Approve 게이트 코드 준비) |
| 6 | Browserless + R2 카드 렌더 | `publish` 시 PNG·URL |
| 7 | 인스타 캐러셀 | Meta 토큰 후 게시 |
| 8 | `seen_urls` + n8n 네이티브 노드화 | **Postgres `seen_urls` 파이프라인 연동됨** / n8n UI는 후속 |
| 9 | (선택) 장후 16:30 마감 브리핑 | 워크플로 복제 |
| 10 | (Phase 2) 네이버 섹션·조회수 랭킹 | 포털면 정렬이 필요할 때 |

**코드로 준비된 단계:** 0–5, 8의 `seen_urls` (5–7 실발행은 `.env` 토큰·Browserless/R2 필요).

## MVP 성공 기준

- [ ] 평일 07:30(또는 Manual)에 Telegram 초안이 온다 (토큰 설정 후 `smoke_telegram` + `MVP_MODE=draft`)
- [x] 초안 뉴스가 **당일** Google News 토픽 기반이다
- [ ] Approve 시 티스토리 글이 생긴다 (코드·DRY_RUN 경로 확인됨; 실토큰 스모크 남음)
- [ ] Approve 시 인스타 5~7장 캐러셀이 올라간다
- [x] 성공 발행한 URL은 다음날 재사용되지 않는다 (`seen_urls` Postgres)
- [ ] 실패 시 단계가 Telegram에 보인다

## 트러블슈팅

| 증상 | 점검 |
|------|------|
| n8n → Ollama 실패 | `docker compose ps ollama`, n8n은 `http://ollama:11434`, 호스트 스크립트는 `OLLAMA_HOST_URL` |
| 포트 11434 충돌 | 기존 Ollama 컨테이너와 중복 → 한쪽 중지 또는 `OLLAMA_PORT` 변경 |
| JSON 파싱 실패 | `format: json`, temperature↓, 7b→14b, 재시도 |
| 당일 기사 0건 | 타임존, `pubDate` 파싱, 주말/연휴 |
| 잡뉴스 과다 | NATION 비중↓, 중요도 감점 강화, WATCHLIST 가점 |
| 카드 한글 깨짐 | 웹폰트/Browserless 폰트 |
| 인스타 `image_url` | R2 URL 공개 HTTPS 여부 |
| 티스토리 401 | 토큰 재발급 |

## 보안

- `.env` git 제외
- 토큰을 워크플로 JSON에 하드코딩하지 않음 (Credentials/환경변수)
- R2는 필요 prefix만 공개
- Meta·티스토리 토큰 주기적 갱신
- 보유 종목·계좌 정보 과다 노출 지양

## 참고 링크

- [n8n](https://docs.n8n.io/)
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [티스토리 Open API](https://www.tistory.com/guide/api/manage/register)
- [Instagram Content Publishing](https://developers.facebook.com/docs/instagram-api/guides/content-publishing/)
- [Cloudflare R2](https://developers.cloudflare.com/r2/)

## 면책

자동화와 생성 콘텐츠의 법적·투자적 책임은 운영자(사용자)에게 있습니다.
