# Runtime Preflight (Phase 7)

`scripts/runtime/preflight.py` checks:

- network (optional ping)
- Ollama `/api/tags`
- database / SQLite fallback path
- output directory writable
- env presence for publishing (no live login)

Bounded recovery (safe only): retry transient network; optional container restart flags via env. Never auto-bypass auth/CAPTCHA.
