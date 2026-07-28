오늘 날짜(Asia/Seoul): {{date}}
target_language: {{target_language}}
target_locale: {{target_locale}}

아래 fact-layer JSON을 요청 받은 대상 언어의 story JSON 초안으로 변환하라.

필수 self-check:
1. 응답이 요청된 언어로만 구성되어 있는가?
2. 다른 언어가 남아 있다면 고유명사/티커/필수 약어 외 모두 치환되었는가?
3. 의미가 원본 fact-layer와 달라지지 않았는가?

```json
{{fact_json}}
```
