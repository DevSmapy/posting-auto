#!/usr/bin/env bash
# Weekday morning draft run (Approve → briefing.md).
# Cron: 0 7 * * 1-5  (NOTIFY_SEND_AT controls Discord send time, default 07:50)
# Usage: ./scripts/run_draft.sh
#
# Starts postgres (+ browserless if cards) and ollama, warms the model, runs the
# pipeline. After LLM work, mvp_pipeline stops ollama *before* Discord Approve.
# Remaining containers stop on EXIT. Disable with OLLAMA_AUTO_CONTAINER=0 /
# DRAFT_AUTO_AUX=0.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Capture caller/cron overrides BEFORE sourcing .env. Otherwise .env's
# MVP_MODE=dry_run (common for manual mvp_pipeline) would win and skip Discord Approve.
# Prefer: CLI env > run_draft defaults > .env (python load_dotenv won't override exports).
_caller_mvp_mode="${MVP_MODE-}"
_caller_rank_mode="${RANK_MODE-}"
_caller_briefing_mode="${BRIEFING_MODE-}"
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

# Morning path: Approve draft + one LLM briefing (ranking heuristic).
export MVP_MODE="${_caller_mvp_mode:-draft}"
export RANK_MODE="${_caller_rank_mode:-heuristic}"
export BRIEFING_MODE="${_caller_briefing_mode:-llm}"
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

draft_start_all

python scripts/mvp_pipeline.py
