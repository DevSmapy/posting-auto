# Runtime Preflight (Phase 7)

`scripts/runtime/preflight.py` checks:

- network (optional ping; soft unless `PREFLIGHT_REQUIRE_NETWORK=1`)
- Ollama `/api/tags` (soft unless `--require-ollama`)
- output directory writable (`OUTPUT_DIR`, default `./output`)
- publish env presence (hard-fail when `AUTO_PUBLISH=1` and live IG publish is selected)

Bounded recovery (safe only): retry transient network; optional container restart flags via env. Never auto-bypass auth/CAPTCHA.

Database connectivity is checked at runtime by `seen_urls` (Postgres → SQLite fallback), not in preflight yet.
