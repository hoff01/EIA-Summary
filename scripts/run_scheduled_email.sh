#!/bin/zsh
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
load_project_env

PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.11/bin:/usr/bin:/bin:/usr/sbin:/sbin"
if ! PYTHON="$(python_bin)"; then
  echo "Python was not found. Run scripts/setup_mac.sh first." >&2
  exit 1
fi

timestamp() {
  date "+%Y-%m-%dT%H:%M:%S%z"
}

cd "$ROOT"
mkdir -p logs

{
  echo "[$(timestamp)] python=$PYTHON"
  echo "[$(timestamp)] starting DOE summary dashboard email"
  "$PYTHON" build.py --refresh-eia-latest --week latest --send-email --email-mode smtp --email-mode mail
  echo "[$(timestamp)] completed DOE summary dashboard email"
} >> "$ROOT/logs/scheduled_email.log" 2>&1
