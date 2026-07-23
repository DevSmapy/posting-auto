#!/usr/bin/env bash
# cron용: 로그인 셸(.zshrc) 없이 docker/PATH 보장
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"
export PYTHONUNBUFFERED=1

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# 진단용 (문제 있을 때만 로그에 남김)
if ! command -v docker >/dev/null 2>&1; then
  echo "!! cron wrapper: docker not in PATH=$PATH" >&2
  exit 1
fi

exec ./scripts/run_draft.sh
