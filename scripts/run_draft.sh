#!/usr/bin/env bash
# Weekday morning draft run (Approve → briefing.md).
# Usage: ./scripts/run_draft.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

export MVP_MODE="${MVP_MODE:-draft}"
# Prefer Discord when configured; otherwise factory falls back.
export NOTIFY_CHANNEL="${NOTIFY_CHANNEL:-}"

exec python scripts/mvp_pipeline.py
