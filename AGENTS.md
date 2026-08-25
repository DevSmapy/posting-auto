# AGENTS.md

## Cursor Cloud specific instructions

This is a Python 3.12+ project managed with **uv** (see `README.md` and `docs/00-mvp-quickstart.md` for the full product/run docs). The core product is a CLI news pipeline (`scripts/mvp_pipeline.py`) that collects Korean economy news, ranks it, and writes a markdown briefing (`briefing.md`). Two optional Streamlit UIs live under `apps/` (`ops_console`, `template_studio`).

Dependency install (`uv sync`) is handled by the environment update script, so it is not repeated here. `uv` lives at `~/.local/bin` (on `PATH` via `~/.profile`/`~/.bashrc`); in a non-login shell prefix commands with `PATH="$HOME/.local/bin:$PATH"`.

### Common commands
- Env file (first run): `cp .env.example .env` (gitignored; safe defaults work offline).
- Tests (no network needed, 207 tests): `uv run python -m unittest discover -s tests`
- Lint: no linter is configured. Use a syntax/byte-compile check: `uv run python -m compileall scripts apps tests`
- Run the pipeline (offline path): `MVP_MODE=dry_run RANK_MODE=heuristic BRIEFING_MODE=heuristic uv run python scripts/mvp_pipeline.py` — writes `output/<timestamp>/` (`candidates.json`, `ranked.json`, `briefing.json`). Requires outbound network to Google News RSS.
- Optional UI: `uv run streamlit run apps/ops_console/app.py --server.headless true --server.port 8501` (health at `/_stcore/health`).

### Non-obvious gotchas
- **`draft`/`publish`/`autonomous` modes force-start Docker containers.** `ensure_runtime_before_llm()` overrides `OLLAMA_AUTO_CONTAINER=0` and runs `scripts/draft_lifecycle.sh` to bring up Ollama + aux containers whenever the Ollama HTTP endpoint is unreachable. With no Docker/Ollama in the VM this **hangs**. For offline verification use `MVP_MODE=dry_run` (it never calls that bootstrap). To exercise `draft`/`publish`, a reachable Ollama at `OLLAMA_HOST_URL`/`OLLAMA_BASE_URL` must exist first.
- **Postgres is optional.** `SEEN_URLS_BACKEND=auto` transparently falls back to SQLite (`./output/seen_urls.sqlite`) when Postgres (`:5433`) is down — the "Postgres seen_urls unavailable … using SQLite fallback" log line is expected, not an error.
- **`docker-compose.yml` volume paths default to macOS external drives** (`/Volumes/WD_BLACK`, `/Volumes/Extreme SSD`). On Linux you must override `POSTGRES_DATA_PATH` / `OLLAMA_DATA_PATH` / `N8N_DATA_PATH` (or skip compose) if you start those services.
- LLM (Ollama), Browserless card rendering (`:3000`), Cloudflare R2, Meta/Instagram, and Discord/Telegram/Slack are all optional and only needed for full LLM briefings or card/Instagram publishing; the markdown-briefing core runs without them via the heuristic path above.
- To render `briefing.md` from a `dry_run` result without the publish/Docker path: `assemble_blog_markdown()` in `scripts/mvp_pipeline.py` (import with `sys.path.insert(0, "scripts")`).
