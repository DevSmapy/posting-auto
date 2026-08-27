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
