# LangGraph Decision (Phase 4)

## Plan default

LangGraph remains the **candidate** orchestrator (§19). Phase 1–3 hook into existing `draft_run` / `mvp_pipeline` first.

## Promote LangGraph when

- Revision / resume / checkpoint complexity clearly exceeds `DraftRunStore`.
- Explicit graph routing reduces bugs vs nested loops.

## Defer when

- `draft_run` parked/resume stays simpler and stable.

**Not abandoned** — revisit after editorial loop is production-stable.
