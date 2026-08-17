# Posting Auto 2.0 — Terminal Monitoring Dashboard 기획 제안서

## 1. 목적

`posting_auto`는 로컬 환경에서 뉴스 수집, 콘텐츠 생성, 검수, 수정, 게시, 검증까지 자동화하는 방향으로 발전하고 있다.

자동화 수준이 높아질수록 운영자는 다음 질문에 빠르게 답할 수 있어야 한다.

- 현재 시스템은 실행 중인가?
- 어느 단계까지 진행됐는가?
- Ollama, PostgreSQL, Docker 등의 런타임 상태는 정상인가?
- 어떤 뉴스가 선택되었고 각 story의 상태는 무엇인가?
- Reviewer가 어떤 story를 수정 요청했는가?
- 현재 어떤 Agent/LLM 작업이 실행 중인가?
- Tistory와 Instagram 게시 상태는 어떻게 되었는가?
- 최근 오류 또는 경고가 무엇인가?

현재는 로그 파일, JSON 결과물, 터미널 출력 등을 개별적으로 확인해야 하므로 autonomous workflow의 운영 상황을 직관적으로 파악하기 어렵다.

따라서 `posting_auto`에 **read-only Terminal Monitoring Dashboard(TUI)** 를 추가한다.

초기 버전의 목표는 시스템을 제어하는 UI가 아니라:

> **현재 상태를 한 화면에서 관찰할 수 있는 lightweight operational console**

을 만드는 것이다.

---

# 2. 핵심 원칙

Dashboard는 다음 원칙을 따른다.

## 2.1 Read-only First

초기 버전에서는 workflow를 제어하지 않는다.

다음 기능은 우선 구현하지 않는다.

```text
retry
pause
resume
force publish
manual approve
kill process
configuration edit
```

Dashboard는 오직 상태를 읽고 보여준다.

향후 필요성이 확인될 경우 별도 Phase에서 control 기능을 추가한다.

---

## 2.2 Dashboard Failure Must Not Affect Pipeline

Dashboard와 `posting_auto` workflow는 강하게 결합하지 않는다.

금지:

```text
Dashboard
↓
directly controls pipeline execution
```

권장:

```text
Posting Auto
↓
State / Events / DB / JSON
↓
Dashboard
```

Dashboard process가 종료되거나 오류가 발생해도 posting pipeline은 정상적으로 계속 실행되어야 한다.

---

## 2.3 Existing State Reuse

새로운 monitoring backend를 과도하게 만들지 않는다.

현재 시스템에서 이미 생성되는 다음 자료를 최대한 활용한다.

예:

```text
run_id
editorial_result.json
quality_gate.json
publish result
runtime preflight result
logs
PostgreSQL state
```

필요한 데이터가 부족한 경우에만 최소한의 event/state emission을 추가한다.

---

## 2.4 Local-first

Dashboard는 M2 MacBook Air에서 posting pipeline과 함께 동작할 수 있어야 한다.

다음과 같은 별도 infrastructure는 추가하지 않는다.

```text
Grafana
Prometheus
Elastic Stack
Redis
Kafka
external monitoring service
cloud dashboard
```

최소 dependency를 우선한다.

---

# 3. 권장 기술

초기 구현 후보:

```text
Python
+
Rich 또는 Textual
```

## Rich

장점:

- 구현이 단순함
- Live refresh 지원
- Table / Progress / Panel 구현이 쉬움
- dependency가 비교적 작음

1차 MVP에 적합하다.

## Textual

장점:

- full-screen TUI
- layout
- tabs
- scrolling
- keyboard event
- 향후 interactive control 확장 용이

장기적으로 dashboard를 발전시킬 계획이라면 적합하다.

---

# 4. 기술 선택 원칙

바로 Textual을 강제하지 않는다.

Cursor AI는 repository audit 후 다음을 비교한다.

```text
Option A — Rich Live Dashboard
Option B — Textual TUI
```

판단 기준:

- 구현 복잡도
- 기존 dependency 영향
- refresh 요구사항
- scrollable log 필요성
- 향후 control console 확장 가능성

추천 기준:

> 단순 read-only MVP라면 Rich 우선  
> 여러 화면/탭/탐색 기능이 필요하면 Textual

---

# 5. Dashboard V1 화면 구성

첫 버전은 하나의 화면에서 다음 5개 영역을 보여주는 것을 목표로 한다.

```text
1. Runtime
2. Pipeline
3. Stories
4. LLM
5. Publishing
```

추가로 가장 최근 event/log를 하단에 표시한다.

---

# 6. 화면 예시

```text
┌──────────────────────────────────────────────────────────────┐
│ Posting Auto 2.0                              07:13:42 KST   │
├──────────────────────────────────────────────────────────────┤
│ RUN  20260817_070001_ab12        MODE  autonomous            │
│ STATE  REVIEW                   ELAPSED  00:12:31            │
├───────────────────────────┬──────────────────────────────────┤
│ RUNTIME                   │ PIPELINE                         │
│                           │                                  │
│ ● Network      healthy    │ ✓ Collect      43 articles      │
│ ● Ollama       healthy    │ ✓ Filter       12 candidates    │
│ · PostgreSQL   unknown    │ ✓ Select        5 stories       │
│ · Renderer     unknown    │ ✓ Write         5 stories       │
│                           │ → Review        3 / 5            │
│                           │ · Editor        pending          │
│                           │ · Render        pending          │
│                           │ · Publish       pending          │
├───────────────────────────┴──────────────────────────────────┤
│ STORIES                                                      │
│ 1 ✓ PASS    미국 금리...                   revision 0        │
│ 2 ↻ REVISE  반도체 관세...                 revision 1        │
│ 3 → REVIEW  서울 부동산...                                  │
│ 4 · WAIT    LG/NVIDIA...                                     │
│ 5 · WAIT    경상수지...                                      │
├──────────────────────────────────────────────────────────────┤
│ LLM                                                          │
│ model: qwen2.5:14b                                           │
│ current role: Reviewer                                       │
│ current duration: 21.4s                                      │
│ calls: 8    revisions: 1    failures: 0                     │
├──────────────────────────────────────────────────────────────┤
│ PUBLISH                                                      │
│ Tistory      pending                                         │
│ Instagram    pending                                         │
├──────────────────────────────────────────────────────────────┤
│ LAST EVENT                                                   │
│ 07:13:38 Reviewer requested content rewrite for story #2     │
└──────────────────────────────────────────────────────────────┘
```

실제 field 이름과 상태는 기존 코드 구조를 우선한다.

---

# 7. Runtime Panel

다음 상태를 가능한 범위에서 표시한다.

V1 활성 체크:

```text
Network
Ollama
```

V1에서는 해당 프로브가 없으므로 PostgreSQL, Docker / required container, Renderer는 표시하지 않거나 `unknown`으로 둔다. 프로브와 state 필드가 생기면 그때 추가한다.

상태 예:

```text
healthy
unavailable
unknown
```

Dashboard가 직접 service recovery를 수행하지 않는다.

Runtime Manager가 recovery를 수행하고 Dashboard는 결과만 표시한다.

---

# 8. Pipeline Panel

현재 workflow의 진행 단계를 표시한다.

초기 stage 후보:

```text
PRECHECK
COLLECT
FILTER
RANK
WRITE
VALIDATE
REVIEW
REVISE
EDITOR
RENDER
PUBLISH
VERIFY
COMPLETE
FAILED
```

각 단계 상태:

```text
pending
running
success
failed
skipped
```

예:

```text
✓ Collect
✓ Filter
✓ Write
→ Review
· Editor
· Publish
```

---

# 9. Story Panel

각 story의 현재 editorial 상태를 표시한다.

예:

```text
WAIT
WRITING
VALIDATING
REVIEW
PASS
REVISE
REJECT
EXCLUDED
```

표시 항목 후보:

```text
story index
short headline
status
revision count
review result
```

예:

```text
1 PASS      미국 금리 동결...        rev 0
2 REVISE    반도체 관세...          rev 1
3 REVIEW    서울 주택가격...
```

헤드라인은 terminal width에 맞춰 truncate한다.

---

# 10. LLM Panel

Ollama workflow 상태를 표시한다.

가능한 항목:

```text
model
current role
current request duration
total calls
failed calls
revision calls
```

Ollama가 runtime statistics를 제공할 경우 다음도 검토할 수 있다.

```text
prompt token count
generated token count
eval duration
tokens/sec
```

단 제공되지 않는 값을 임의로 계산하거나 추정하지 않는다.

---

# 11. Publishing Panel

각 publishing channel 상태를 표시한다.

예:

```text
Tistory
Instagram
Markdown
```

상태:

```text
pending
publishing
success
failed
skipped
auth_required
```

가능하면 성공 시 간략한 identifier를 제공한다.

예:

```text
Tistory    success
Instagram  success · media_id=...
```

긴 URL은 기본 화면에 출력하지 않는다.

---

# 12. Event / Log Panel

최근 event를 시간순으로 표시한다.

V1에서는 가장 최근 1~5건만 보여주는 것으로 충분하다.

예:

```text
07:13:38 reviewer → revise story #2
07:13:41 writer revision started
07:14:03 writer revision completed
```

향후 Textual을 사용할 경우 scrollable log view로 확장할 수 있다.

---

# 13. Dashboard State Model

Dashboard 전용으로 pipeline 내부 상태를 직접 읽어 조합하지 않는다.

가능하면 표준화된 monitoring state를 만든다.

예:

```python
class DashboardState:
    run_id: str
    mode: str
    started_at: datetime

    pipeline_stage: str
    pipeline_status: dict

    runtime_status: dict

    stories: list

    llm_status: dict

    publish_status: dict

    recent_events: list
```

그러나 새로운 domain model을 과도하게 만들지 않는다.

기존 `EditorialState`, run metadata, JSON artifacts를 재사용할 수 있다면 우선 재사용한다.

---

# 14. State Source 우선순위

가능한 설계:

```text
Pipeline
   ↓
structured state/events
   ↓
JSON / PostgreSQL
   ↓
Dashboard Reader
   ↓
TUI
```

Dashboard는 pipeline Python object에 직접 접근하지 않는다.

이를 통해 dashboard와 pipeline lifecycle을 분리한다.

---

# 15. Event Emission

현재 정보만으로 dashboard 표현이 어려운 경우 최소 event emission layer를 추가한다.

예:

```json
{
  "timestamp": "...",
  "run_id": "...",
  "component": "reviewer",
  "event": "revision_requested",
  "story_id": "story-2",
  "message": "analysis depth insufficient"
}
```

필수 목적은 monitoring이며 event-driven architecture 자체를 만드는 것이 아니다.

Kafka, message queue 등은 도입하지 않는다.

---

# 16. Refresh Strategy

V1에서는 polling으로 충분하다.

예:

```text
refresh interval:
0.5–2 seconds
```

권장 기본값:

```text
1 second
```

event streaming이나 websocket은 필요하지 않다.

Dashboard 때문에 posting workflow의 architecture를 복잡하게 만들지 않는다.

---

# 17. Dashboard 실행 방식

별도 process로 실행한다.

예:

```bash
uv run python scripts/dashboard.py
```

또는 package 구조 변경 후:

```bash
uv run posting-auto dashboard
```

둘 중 어떤 방식이 현재 repository 구조와 맞는지 audit 후 결정한다.

---

# 18. No Active Run 상태

pipeline이 실행되지 않는 상태에서도 Dashboard가 정상적으로 실행되어야 한다.

예:

```text
Posting Auto 2.0

STATUS: IDLE

Last run:
2026-08-17 07:00
SUCCESS

Next scheduled run:
unknown / configured time

Runtime:
Ollama       available
PostgreSQL   available
```

scheduler에서 다음 실행 시간을 쉽게 읽을 수 없는 경우 `unknown`으로 표시하고 별도 기능을 억지로 만들지 않는다.

---

# 19. Completed Run 상태

run이 종료된 후에도 가장 최근 결과를 보여줄 수 있으면 좋다.

예:

```text
STATUS: COMPLETE

Stories: 5
Revisions: 1
Tistory: success
Instagram: success
Duration: 14m 32s
```

즉 Dashboard는 live monitor이면서 간단한 latest-run summary 역할도 할 수 있다.

---

# 20. Failure 상태

오류 발생 시 가장 중요한 정보가 눈에 띄어야 한다.

예:

```text
STATUS: ACTION REQUIRED

Stage:
TISTORY_PUBLISH

Failure:
AUTH_FAILURE

Reason:
Authentication session expired.

Generated assets preserved:
YES
```

전체 traceback을 메인 화면에 표시하지 않는다.

필요한 경우 log file path를 표시한다.

---

# 21. Dashboard와 Autonomous Operation 관계

Dashboard는 autonomous workflow의 prerequisite가 아니다.

즉:

```text
dashboard OFF
→ posting-auto works

dashboard ON
→ posting-auto works + visibility
```

가 되어야 한다.

---

# 22. Phase 계획

## Phase 0 — Monitoring Audit

Cursor AI는 먼저 현재 repository에서 다음을 조사한다.

```text
run state는 어디에 있는가?
editorial state는 어디에 저장되는가?
quality result는 어디에 저장되는가?
runtime preflight 결과는 어디에 있는가?
publisher 결과는 어디에 저장되는가?
현재 log format은 무엇인가?
```

결과를 간단히 보고한다.

---

## Phase 1 — Dashboard State Adapter

기존 정보를 읽어 하나의 view model로 정규화한다.

새 persistence layer를 만들지 않는다.

---

## Phase 2 — Read-only Dashboard MVP

다음 panel을 구현한다.

```text
Runtime
Pipeline
Stories
LLM
Publishing
Latest Event
```

---

## Phase 3 — Live Run Validation

실제 autonomous dry run을 실행하며 확인한다.

검증:

```text
stage transition 반영
story status 반영
revision 반영
LLM status 반영
publish status 반영
failure display
```

---

## Phase 4 — UX 개선

실제 사용 후 필요한 부분만 개선한다.

예:

```text
layout
status symbols
terminal resize
long headline truncation
log visibility
idle state
completed state
```

---

# 23. Future Phase — Interactive Console

V1 이후 필요성이 확인되면 다음을 검토할 수 있다.

```text
pause
resume
retry failed stage
open generated file
show story detail
show reviewer reason
manual publish
```

하지만 이는 별도 proposal로 취급한다.

초기 Dashboard 구현에 포함하지 않는다.

---

# 24. UX 원칙

Terminal UI는 정보를 많이 보여주는 것이 목표가 아니다.

다음 세 질문에 즉시 답할 수 있어야 한다.

> 시스템은 정상인가?
> 지금 무엇을 하고 있는가?
> 내가 개입해야 하는가?

모든 정보는 이 질문 중 하나에 기여해야 한다.

---

# 25. Status 표현

가능하면 일관된 symbol을 사용한다.

예:

```text
✓ success
→ running
· pending
↻ revision/retry
! warning
✗ failed
```

색상은 보조 표현으로만 사용한다.

색상이 없어도 상태를 이해할 수 있어야 한다.

---

# 26. 성능 요구사항

Dashboard는 posting pipeline의 자원 사용량에 의미 있는 영향을 주면 안 된다.

원칙:

```text
no LLM calls
no heavy database queries
no aggressive polling
no rendering browser
```

Dashboard 자체는 lightweight process여야 한다.

---

# 27. Error Handling

Dashboard reader에서 일부 state를 읽지 못해도 전체 화면이 종료되지 않아야 한다.

예:

```text
Ollama status unavailable

→ show UNKNOWN
```

반대로:

```text
Dashboard crash
```

가 되어서는 안 된다.

---

# 28. Testing

최소 다음 상태를 fixture 또는 mock으로 테스트한다.

```text
IDLE
RUNNING
REVISING
PUBLISHING
COMPLETE
FAILED
PARTIAL FAILURE
```

또한:

```text
missing state file
corrupt JSON
database unavailable
terminal resize
```

상황에서도 안전하게 동작해야 한다.

---

# 29. Acceptance Criteria

V1 완료 기준:

- Dashboard가 별도 process로 실행된다.
- Dashboard 없이 기존 posting workflow가 동일하게 동작한다.
- 현재 run ID와 mode를 표시한다.
- 현재 pipeline stage를 표시한다.
- 주요 runtime dependency 상태를 표시한다.
- story별 review/revision 상태를 표시한다.
- 현재 LLM role/model 정보를 가능한 범위에서 표시한다.
- channel별 publish 상태를 표시한다.
- 가장 최근 event 또는 error를 표시한다.
- IDLE / RUNNING / COMPLETE / FAILED 상태를 구분한다.
- state 일부가 누락되어도 dashboard 전체가 crash하지 않는다.
- M2 MacBook Air에서 의미 있는 추가 resource burden 없이 동작한다.

---

# 30. Cursor AI 구현 원칙

## 1. Audit First

현재 monitoring 가능한 state를 먼저 조사한다.

## 2. Do Not Modify Core Workflow Unnecessarily

Dashboard를 위해 editorial pipeline을 크게 재작성하지 않는다.

## 3. Read-only

V1에서는 pipeline control 기능을 추가하지 않는다.

## 4. Reuse Existing State

새 database/table/event system을 만들기 전에 기존 JSON/DB/log를 활용한다.

## 5. No Heavy Infrastructure

모니터링을 위해 별도 server stack을 만들지 않는다.

## 6. Preserve Pipeline Independence

Dashboard failure가 pipeline failure가 되면 안 된다.

## 7. Keep UI Simple

terminal에서 현재 상태를 빠르게 읽을 수 있는 것이 우선이다.

## 8. Report Decision if UI Framework Choice Is Ambiguous

Rich와 Textual 중 선택이 필요한 경우 다음 형식으로 먼저 보고한다.

```text
Option A: Rich
Benefits:
...

Option B: Textual
Benefits:
...

Recommendation:
...

Reason:
...
```

---

# 31. Cursor AI 첫 작업 요청

본 기획서를 받은 뒤 바로 UI부터 작성하지 않는다.

먼저 다음을 확인하고 짧은 보고를 작성한다.

```text
1. 현재 run state source
2. editorial result source
3. quality/revision state source
4. runtime health source
5. publishing result source
6. current log/event structure
7. Dashboard에서 그대로 재사용 가능한 데이터
8. 추가 emission이 필요한 데이터
9. Rich vs Textual 추천
10. 예상 파일 변경 범위
```

이후 최소 변경으로 Dashboard MVP를 구현한다.

---

# 32. Long-term Direction

이번 기능의 장기적인 목적은 화려한 terminal UI를 만드는 것이 아니다.

`posting_auto`가 autonomous system으로 발전할수록 운영자는 내부 구현을 직접 확인하는 대신 하나의 operational surface를 통해 상태를 파악할 수 있어야 한다.

최종적으로는:

```text
Local Runtime
      ↓
Autonomous Editorial Pipeline
      ↓
State / Events
      ↓
Terminal Operations Dashboard
```

구조를 지향한다.

Dashboard는 다음 질문을 한 화면에서 답할 수 있어야 한다.

> **지금 Posting Auto는 살아 있는가?**
> **현재 무엇을 하고 있는가?**
> **정상적으로 끝날 가능성이 높은가?**
> **사람이 개입해야 하는 문제가 발생했는가?**

이 네 가지를 명확하게 보여주는 것이 Terminal Dashboard V1의 성공 기준이다.
