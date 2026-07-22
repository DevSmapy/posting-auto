#!/usr/bin/env bash
# Weekday morning draft run (Approve → briefing.md).
# Cron: 0 7 * * 1-5  (NOTIFY_SEND_AT controls Discord send time, default 07:50)
# Usage: ./scripts/run_draft.sh
#
# Starts the ollama container, warms the model, runs the pipeline, then unloads
# the model and stops the container (trap EXIT) so RAM is freed between runs.
# Disable with OLLAMA_AUTO_CONTAINER=0.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

# Morning path: one LLM call for briefing (ranking stays heuristic).
export RANK_MODE="${RANK_MODE:-heuristic}"
export BRIEFING_MODE="${BRIEFING_MODE:-llm}"
export MVP_MODE="${MVP_MODE:-draft}"
# Prefer Discord when configured; otherwise factory falls back.
export NOTIFY_CHANNEL="${NOTIFY_CHANNEL:-}"
export OLLAMA_AUTO_CONTAINER="${OLLAMA_AUTO_CONTAINER:-1}"

# shellcheck disable=SC1091
source "$ROOT/scripts/ollama_lifecycle.sh"

cleanup() {
  ollama_cleanup_container || true
}
trap cleanup EXIT

ollama_start_container
ollama_warm_model

python scripts/mvp_pipeline.py
