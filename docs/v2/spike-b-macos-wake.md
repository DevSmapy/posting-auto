# Spike B — macOS Sleep/Wake (M2)

Operator checklist on the reference MacBook Air M2. **Not** Shutdown/Boot/FileVault unlock.

## Test 1 — Sleep → Wake → process

1. User already logged in; power adapter preferred.
2. Schedule wake (Energy Saver / `pmset` / Calendar) for +5–10 minutes.
3. Put Mac to sleep (lid closed or Apple menu → Sleep).
4. After wake, confirm:
   - [ ] Network reconnects
   - [ ] `curl -s http://127.0.0.1:11434/api/tags` succeeds (or start Ollama)
   - [ ] `uv run python -c "print('ok')"` in project dir succeeds
5. Record lid open/closed, battery %, adapter yes/no.

## Test 2 — Screen locked + headless browser

1. Lock screen (not logout).
2. From SSH/another session or scheduled job, run a headless Chromium screenshot (Browserless or local).
3. Record: works / fails / needs unlock.

## Results log

| Date | Lid | Adapter | Wake OK | Ollama | Python | Locked headless | Notes |
|------|-----|---------|---------|--------|--------|-----------------|-------|
| | | | | | | | |

Shutdown → Boot automation is out of scope (Human Exception).
