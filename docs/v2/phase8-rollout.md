# Controlled autonomous rollout (Phase 8)

```text
dry_run
 → MVP_MODE=autonomous AUTO_PUBLISH=false  (editorial decision + package)
 → single-channel (IG package/publish) when credentials ready
 → dual-channel after Tistory Spike A promotion
 → scheduled unattended after Spike B pass
```

Commands:

```bash
uv run python scripts/runtime/preflight.py
MVP_MODE=autonomous AUTO_PUBLISH=false NOTIFY_CHANNEL=auto \
  BRIEFING_MODE=heuristic \
  uv run python scripts/mvp_pipeline.py
```

Do not enable `AUTO_PUBLISH=true` until editorial fixtures and a local dry run look good.
