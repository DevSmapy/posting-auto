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

Instagram 풀 자동화 전에 dry-run의 `seen_urls` 오염, Story 단위 reject 미동작, 한국어 language hard gate, Final Publish Guard, 단일 실행 lock, fail-closed 정책을 고정한다. 목적은 정상 실행은 무인 게시하고, 품질·언어·런타임·외부 게시 실패 시에는 게시를 막고 산출물을 보존한 뒤 운영자에게 알리는 게시 경계를 완성하는 것이다. 이 문서는 구현 착수 전 계획이며, 코드 변경은 아직 없다.

### Changes

_(구현 착수 전 — 변경 없음)_

### Notes

#### Todos

- [ ] `run_publish` `persist_seen` 분리: dry `never` / live `after_ig` / draft `after_export`
- [ ] `editor_decide` cascade 제거 + exclude reasons + caption/html 재조립
- [ ] 한국어 language hard gate + rewrite/exclude 루프
- [ ] Final Publish Guard + `publish_guard.json` + fail-closed
- [ ] `run_status.json` 전이 + autonomous single-run lock
- [ ] 요구 시나리오 1–15 unittest + mock publisher
- [ ] 10항목 완료 보고 (미실행 검증은 `not executed`)

#### 범위에서 제외

- Tistory 실게시 승격
- macOS Sleep/Wake 자동화
- LangGraph 도입
- n8n 제거
- 별도 대시보드/UI
- Cloud LLM 전환

#### 기본 결정

- Dry-run(`AUTO_PUBLISH=false`): `record_published` / `seen_urls` 미기록. 상태는 run 산출물만.
- Draft Approve: 기존처럼 export 직후 `record_published` 유지.
- Autonomous live: Instagram `media_id` 성공 시에만 `record_published`.

#### 운영 검증 (구현 후)

1. Wave 1 — dry-run (`AUTO_PUBLISH=false`, `EDITORIAL_LLM_REVIEWER=1`)
2. Wave 2 — Instagram 실게시 1회 (Wave 1 정상 후, 운영자 승인)
3. 스케줄러 연결은 Wave 2 이후

상세 설계·파일 단위 작업은 이 PR의 후속 커밋으로 반영한다.
