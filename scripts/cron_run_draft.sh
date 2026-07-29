#!/usr/bin/env bash
# cron용: 로그인 셸(.zshrc) 없이 docker/PATH 보장
# Ops console: config/ops.json 의 run_at/weekdays 와 맞을 때만 draft 실행.
# crontab 예: */5 * * * 1-5 "/ABS/scripts/cron_run_draft.sh" >>"/ABS/output/cron.log" 2>&1
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"
export PYTHONUNBUFFERED=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Prefer uv (same as run_draft.sh). Fall back to .venv / python3.
if command -v uv >/dev/null 2>&1; then
  run_py() { uv run python "$@"; }
elif [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  run_py() { python "$@"; }
else
  run_py() { python3 "$@"; }
fi

# 진단용 (문제 있을 때만 로그에 남김)
if ! command -v docker >/dev/null 2>&1; then
  echo "!! cron wrapper: docker not in PATH=$PATH" >&2
  exit 1
fi

if ! run_py "$ROOT/scripts/ops_config.py"; then
  exit 0
fi

./scripts/run_draft.sh
status=$?
if [[ "$status" -eq 0 ]]; then
  run_py "$ROOT/scripts/ops_config.py" --mark-run || true
fi
exit "$status"
