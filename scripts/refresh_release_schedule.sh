#!/bin/zsh
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
load_project_env

if ! PYTHON_BIN="$(python_bin)"; then
  echo "Python was not found. Run scripts/setup_mac.sh first." >&2
  exit 1
fi

cd "$ROOT"
mkdir -p "$ROOT/logs"
"$PYTHON_BIN" run_release_gate.py --refresh-schedule-only --force-schedule-refresh
