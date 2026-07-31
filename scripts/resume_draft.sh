#!/usr/bin/env bash
# Resume a parked content/render gate for an existing run directory.
# Usage: ./scripts/resume_draft.sh output/<run_id>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 output/<run_id>" >&2
  exit 1
fi

RUN_DIR="$1"

if command -v uv >/dev/null 2>&1; then
  run_py() { uv run python "$@"; }
elif [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  run_py() { python "$@"; }
else
  run_py() { python3 "$@"; }
fi

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

export MVP_MODE="${MVP_MODE:-draft}"
export OLLAMA_AUTO_CONTAINER="${OLLAMA_AUTO_CONTAINER:-1}"
export DRAFT_AUTO_AUX="${DRAFT_AUTO_AUX:-1}"

# shellcheck disable=SC1091
source "$ROOT/scripts/draft_lifecycle.sh"

cleanup() {
  draft_cleanup_all || true
}
trap cleanup EXIT

draft_start_llm_runtime
run_py scripts/resume_draft.py "$RUN_DIR"
