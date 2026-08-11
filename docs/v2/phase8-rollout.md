# Controlled autonomous rollout (Phase 8)

```text
dry_run
 → MVP_MODE=autonomous AUTO_PUBLISH=false  (editorial decision + package)
 → read editorial_report.md
 → single-channel (IG) when credentials ready
 → dual-channel after Tistory Spike A promotion (later)
 → scheduled unattended after Spike B pass (later)
```

## Commands

```bash
uv run python scripts/runtime/preflight.py

# Dry editorial (no live IG)
MVP_MODE=autonomous AUTO_PUBLISH=false NOTIFY_CHANNEL=auto \
  uv run python scripts/mvp_pipeline.py
# Inspect: output/<run>/attempts/content-01/editorial_report.md
```

Do not enable `AUTO_PUBLISH=true` until a dry run + `editorial_report.md` look good.

## Wave 2 — Instagram live (operator)

**2026-08-11:** Live Graph publish **not** executed.

`.env` has some R2 URL fields, but `IG_USER_ID` / `META_ACCESS_TOKEN` (and some R2 secrets) are empty after dotenv parse → `publish_env` fails when `AUTO_PUBLISH=1 PUBLISH_CARDS=1`. Fill tokens before live run.

```bash
AUTO_PUBLISH=1 PUBLISH_CARDS=1 uv run python scripts/runtime/preflight.py
# need publish_env: ok

MVP_MODE=autonomous AUTO_PUBLISH=true PUBLISH_CARDS=1 \
  NOTIFY_CHANNEL=discord \
  uv run python scripts/mvp_pipeline.py
```

| Date | Result | Notes |
|------|--------|-------|
| 2026-08-11 | deferred | Meta/IG tokens empty; no live post |
