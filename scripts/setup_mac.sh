#!/bin/zsh
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/common.sh"
load_project_env

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv "$ROOT/.venv"
  elif command -v python >/dev/null 2>&1; then
    python -m venv "$ROOT/.venv"
  else
    echo "Python 3.11+ was not found." >&2
    exit 1
  fi
fi

ensure_recipients_file
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
mkdir -p "$ROOT/logs"

echo "Setup complete."
echo "Review $ROOT/email_recipients.txt and optionally copy .env.example to .env for SMTP settings."
