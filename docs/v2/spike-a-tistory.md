# Spike A — Tistory Playwright

## Goal

Authenticated session → editor → test title/body → **draft/private** save → verify.

## Harness

```bash
# storage state MUST stay outside the repo (gitignore)
export TISTORY_STORAGE_STATE="$HOME/.config/posting-auto/tistory-storage.json"
export TISTORY_BLOG_URL="https://YOUR.tistory.com/manage/newpost"
uv run python scripts/spikes/tistory_draft.py --dry-check
# live (writes draft only when --publish-draft):
uv run python scripts/spikes/tistory_draft.py --publish-draft
```

## Checklist (fill after live run)

| Check | Result | Notes |
|-------|--------|-------|
| harness / dry-check | ready | `scripts/spikes/tistory_draft.py` |
| headless possible | pending | needs `TISTORY_STORAGE_STATE` outside repo |
| session persistence | pending | |
| content injection | pending | best-effort selectors only |
| image upload | pending | |
| category/tag | pending | |
| publish / draft action | pending | `--publish-draft` gated |
| published/draft URL | pending | |
| selector stability | pending | |

**2026-08-10:** Live browser spike not executed in this environment (no storage state / playwright session). Target A **not** promoted.

## Decision rule

Failure → do **not** treat Tistory auto-publish as architecture invariant. Keep `briefing.md` + `publish_ready` + Human Escalation. Target A not promoted.
