#!/usr/bin/env bash
# cron용: 로그인 셸(.zshrc) 없이 docker/PATH 보장
# Ops: config/ops.json 의 run_at/weekdays 와 맞을 때만 Wave 1 (autonomous) 실행.
# draft Approve 경로는 타지 않는다 (AUTO_PUBLISH=false, 인스타 실게시 없음).
# crontab 예: 0 6 * * 1-5 "/ABS/scripts/cron_run_draft.sh" >>"/ABS/output/cron.log" 2>&1
# macOS /etc/newsyslog.d/posting-auto.conf 예 (1MB, 압축본 5개 보관):
# /ABS/output/cron.log  640  5  1024  *  J
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

if ! scheduled_day="$(run_py "$ROOT/scripts/ops_config.py" --scheduled-day)"; then
  exit 0
fi
echo "==> ops schedule: run (scheduled date ${scheduled_day})"

# Force Wave 1 so .env MVP_MODE=draft/dry_run cannot resurrect the old morning path.
export MVP_MODE=autonomous
export AUTO_PUBLISH=false
export EDITORIAL_LLM_REVIEWER=1
export NOTIFY_CHANNEL=auto

./scripts/run_draft.sh
status=$?
if [[ "$status" -eq 0 ]]; then
  run_py "$ROOT/scripts/ops_config.py" --mark-run "$scheduled_day" || true
fi
exit "$status"
