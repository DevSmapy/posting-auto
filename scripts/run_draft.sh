#!/usr/bin/env bash
# Pipeline wrapper: start ollama/aux, warm model, run mvp_pipeline, stop on exit.
#
# Morning cron (cron_run_draft.sh): Wave 1 autonomous; 5-min poller + ops.json schedule.
# Manual draft gates: ./scripts/run_draft.sh  (default MVP_MODE=draft)
# Render gate attaches the 1080×1080 site infographic first, then Instagram cards.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer uv (docs assume uv). Fall back to an existing .venv if uv is absent.
if command -v uv >/dev/null 2>&1; then
  run_py() { uv run python "$@"; }
elif [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  run_py() { python "$@"; }
else
  run_py() { python3 "$@"; }
fi

# Capture caller/cron overrides BEFORE sourcing .env. Otherwise .env's
# MVP_MODE=dry_run (common for manual mvp_pipeline) would win and skip Discord Approve.
# Prefer: CLI env > run_draft defaults > .env (python load_dotenv won't override exports).
_caller_mvp_mode="${MVP_MODE-}"
_caller_rank_mode="${RANK_MODE-}"
_caller_briefing_mode="${BRIEFING_MODE-}"
_caller_auto_publish="${AUTO_PUBLISH-}"
_caller_editorial_llm="${EDITORIAL_LLM_REVIEWER-}"
_caller_auto_container="${OLLAMA_AUTO_CONTAINER-}"
_caller_auto_aux="${DRAFT_AUTO_AUX-}"
_caller_notify_from_cli=0
if [ "${NOTIFY_CHANNEL+set}" = set ]; then
  _caller_notify_channel="$NOTIFY_CHANNEL"
  _caller_notify_from_cli=1
fi

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

# Match mvp_pipeline.py (.lower()) so AUTONOMOUS selects the same branch.
MVP_MODE="$(printf '%s' "${_caller_mvp_mode:-draft}" | tr '[:upper:]' '[:lower:]')"
export MVP_MODE
export BRIEFING_MODE="${_caller_briefing_mode:-llm}"
if [ "$MVP_MODE" = "autonomous" ]; then
  # Wave 1: no Approve gates, no Instagram live.
  export AUTO_PUBLISH="${_caller_auto_publish:-false}"
  export EDITORIAL_LLM_REVIEWER="${_caller_editorial_llm:-1}"
  export RANK_MODE="${_caller_rank_mode:-${RANK_MODE:-llm}}"
else
  export RANK_MODE="${_caller_rank_mode:-heuristic}"
fi
# Prefer Discord when configured; otherwise factory falls back.
if [ "$_caller_notify_from_cli" = 1 ]; then
  export NOTIFY_CHANNEL="$_caller_notify_channel"
else
  export NOTIFY_CHANNEL="${NOTIFY_CHANNEL:-}"
fi
export OLLAMA_AUTO_CONTAINER="${_caller_auto_container:-1}"
export DRAFT_AUTO_AUX="${_caller_auto_aux:-1}"

# shellcheck disable=SC1091
source "$ROOT/scripts/draft_lifecycle.sh"

cleanup() {
  draft_cleanup_all || true
}
trap cleanup EXIT

# Content phase: ollama only. Postgres/browserless start before render gate in Python.
draft_start_llm_runtime

run_py scripts/mvp_pipeline.py
