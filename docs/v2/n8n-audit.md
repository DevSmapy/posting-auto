# n8n Audit (Phase 5 prep)

## Repository

- Production path: host Python (`mvp_pipeline.py` / `run_draft.sh`).
- No `econ-briefing-daily.json` in repo.
- `workflows/code-nodes/` = samples only.
- Compose `n8n` service = optional full stack.

## Live machine (operator)

Confirm whether any schedule/webhook still calls this project from external n8n (e.g. WD_BLACK `n8n_data`):

- [ ] No live n8n → document-only cleanup later (Phase 5).
- [ ] Live n8n → map nodes → Python replacement → regression → disable → remove (§38).

Do not delete n8n first.
