# 08. Posting Auto 2.0 — Phase 0 Audit

원 기획서 `Posting Auto 2.0.md` §56 요구 감사. 구현 착수 전 스냅샷.

| 항목 | 요약 |
|------|------|
| Architecture | 호스트 Python `scripts/mvp_pipeline.py` 본체. n8n은 저장소상 후속·optional. |
| Entry points | `run_draft.sh`, `MVP_MODE=dry_run\|draft\|publish`, `cron_run_draft.sh`, `resume_draft.sh` |
| n8n | 네이티브 워크플로 JSON 없음. `workflows/code-nodes/` 샘플만. 실기기 외부 n8n 사용 여부는 운영 확인. |
| Ollama | layered story (fact→translate→polish). Reviewer/Editor 없음. |
| Approval | content / render / cleanup 게이트. `publish`·`NOTIFY_CHANNEL=auto`는 검수 우회. |
| Publishing | `briefing.md` 수동 Tistory, `publish_ready`, IG Graph 코드 있음(운영 미확정). |
| Runtime | Postgres/SQLite `seen_urls`, Browserless/Chrome, cron. formal preflight 없음. |
| DB | `seen_urls` + 파일 `manifest.json`. Run/Publication/Editorial Result 전용 스키마 없음. |
| Reuse | RSS, seen_urls, story_quality, cards, publish, notify, draft_run. |
| High risk | Tistory Playwright, Sleep/Wake, local Reviewer 품질, M2 RAM, 게이트 조기 제거. |

Integration branch: `refactor/v2-autonomous-editorial`.

Spike 결과·체크리스트: [docs/v2/](v2/).
