# Posting Auto 2.0 — 게시 경계 완성 (계획)

Instagram 풀 자동화(`MVP_MODE=autonomous`)를 안전하게 켜기 위한 기술적 마무리 계획이다. **기능 확장보다 게시 경계를 완성**하는 것이 목표다.

정상 경로에서는 사람 승인 없이 게시하고, 품질·언어·런타임·외부 게시에 문제가 있으면 게시를 중단한 뒤 산출물을 보존하고 `ACTION REQUIRED`로 알린다.

```text
정상 경로 → 무인 자동 게시
예외 경로 → 게시 차단 + 산출물 보존 + ACTION REQUIRED 알림
```

기존 `MVP_MODE=draft` 사람 승인 경로는 유지한다. 구현 범위는 `autonomous` 중심이다.

---

### Summary

Instagram 풀 자동화 전에 dry-run `seen_urls` 오염, Story 단위 reject, 한국어 language hard gate, Final Publish Guard, 단일 실행 lock, fail-closed 정책을 고정한다. autonomous live는 `EDITORIAL_LLM_REVIEWER=1` 필수이며, 언어 실패 Story는 제외 후 최소 개수면 게시하고 운영자에게 알린다.

### Changes

- `run_publish(persist_seen=after_export|never|after_ig)` — dry는 seen 미기록, live는 IG 성공 후만 기록
- `editor_decide` — per-story 제외 + `excluded_reasons`, cascade 제거
- `story_quality` — `assess_korean_text` / `language_hard_fail_issues` 다층 gate
- `publish/guard.py` — `assert_publish_ready` + `publish_guard.json` (live 전용 blocker)
- `runtime/run_lock.py` — autonomous single-run lock
- `reviewer.py` — LLM 실패 fail-closed (reject)
- `run_autonomous` — lock, rebuild surfaces, exclusion notify, guard 연동

### Notes

#### Todos

- [x] `run_publish` `persist_seen` 분리
- [x] `editor_decide` cascade 제거 + exclude reasons + caption/html 재조립
- [x] 한국어 language hard gate + rewrite/exclude + 최종 surface 재검사
- [x] Final Publish Guard + fail-closed live
- [x] autonomous single-run lock
- [x] 회귀 테스트 (run_publish, language_gate, publish_guard, run_lock, editorial)
- [ ] Wave 1 dry-run — operator pending
- [ ] Wave 2 IG live 1회 — operator pending

#### 운영자 결정

- **A1:** autonomous live는 `EDITORIAL_LLM_REVIEWER=1` 필수
- **A2:** 언어 hard_fail revision 초과 → Story 제외, min 충족 시 게시 + 알림

#### 운영 검증

1. Wave 1 — `MVP_MODE=autonomous AUTO_PUBLISH=false EDITORIAL_LLM_REVIEWER=1`
2. Wave 2 — Instagram 실게시 1회 (Wave 1 정상 후)

#### 테스트 실행

```bash
uv run python -m unittest discover -s tests -v
```

#### 범위에서 제외

Tistory 승격, Sleep/Wake, LangGraph, n8n, 대시보드, Cloud LLM
