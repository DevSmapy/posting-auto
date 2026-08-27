# 장전 브리핑 사이트

`posting_auto`의 자체 publication V1이다. 정적 HTML만 만든다.

```bash
cd website
npm install
npm run dev
npm run build
```

- 글꼴: Pretendard Variable (`public/fonts`, SIL OFL)
- 콘텐츠: `src/content/posts/*.md`
- 사이트 URL: `SITE_BASE_URL` (없으면 `https://briefing.example`)

파이프라인 환경 변수:

- `WEBSITE_PUBLISH` 기본 `1`. `0`이면 사이트 글을 쓰지 않음
- `WEBSITE_POSTS_DIR` 기본 `website/src/content/posts`
- `WEBSITE_DRY_RUN=1`이면 파일을 쓰지 않음
- `WEBSITE_GIT_PUSH=1`이면 글 파일 git commit/push
- `SITE_BASE_URL`이 있으면 배포 URL을 HTTP로 확인
