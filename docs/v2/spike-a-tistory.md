# Spike A — Tistory Playwright

## Goal

Authenticated session → editor → test title/body → **click draft-save** → confirm success signal or draft URL.

`--publish-draft` only reports success after the draft-save action is confirmed. Filling fields alone is treated as failure.

## Harness

```bash
# storage state MUST stay outside the repo (gitignore)
export TISTORY_STORAGE_STATE="$HOME/.config/posting-auto/tistory-storage.json"
export TISTORY_BLOG_URL="https://YOUR.tistory.com/manage/newpost"
uv run python scripts/spikes/tistory_draft.py --dry-check
# live: fill + click draft-save + confirm (not public publish)
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

**2026-08-10:** Live browser spike not executed (no storage state / playwright session). Target A **not** promoted.

**2026-08-11:** Still pending operator live run. Production `TistoryPublisher` remains stub — checklist fill ≠ production promotion.

## Decision rule

Failure → do **not** treat Tistory auto-publish as architecture invariant. Keep `briefing.md` + `publish_ready` + Human Escalation. Target A not promoted.
