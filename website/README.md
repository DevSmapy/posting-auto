# 장전 브리핑 사이트

`posting_auto`의 자체 publication V1이다. 정적 HTML만 만든다.

```bash
cd website
npm install
npm run dev
npm test
SITE_BASE_URL=https://briefing.example npm run build
```

- 글꼴: Pretendard Variable (`public/fonts`, SIL OFL)
- 콘텐츠: `src/content/posts/*.md`
- 사이트 URL: `SITE_BASE_URL`. `astro build`에는 필수이지만, Vercel 빌드는 `VERCEL_PROJECT_PRODUCTION_URL` / `VERCEL_URL`로 채운다. `astro dev`만 비어 있으면 `https://briefing.example`를 쓴다.
- 호스팅: Vercel 프로젝트 `jangjeon-briefing`. 저장소 루트 `vercel.json`이 `website/`를 빌드한다. GitHub 앱을 연결하면 브랜치 푸시가 프리뷰, `main`이 프로덕션이다.

파이프라인 환경 변수:

- `WEBSITE_PUBLISH` 기본 `1`. `0`이면 사이트 글을 쓰지 않음
- `WEBSITE_POSTS_DIR` 기본 `website/src/content/posts`
- `WEBSITE_DRY_RUN=1`이면 파일을 쓰지 않음
- `WEBSITE_GIT_PUSH=1`이면 글 파일 git commit/push
- `WEBSITE_INFOGRAPHIC` 기본 `1`. 승인 글을 쓸 때 1080×1080 인포그래픽 PNG를 같이 만든다. Chrome이 없으면 글만 쓴다
- 홈·글 목록·OG 이미지는 이 인포그래픽을 쓴다. 가로 커버는 없을 때만 쓴다
- `WEBSITE_IMAGES_DIR` 기본 `website/public/images/posts`
- `SITE_BASE_URL`이 있으면 배포 URL을 HTTP로 확인
- 초안은 `./scripts/run_draft.sh` (렌더 게이트에 인포그래픽이 먼저 첨부됨)

픽스처 인포그래픽을 다시 그리려면:

```bash
uv run python -m publish.site_graphics
```
