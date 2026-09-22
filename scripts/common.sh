#!/bin/zsh
set -euo pipefail

if [[ -n "${ZSH_VERSION-}" ]]; then
  _COMMON_SOURCE="${(%):-%N}"
else
  _COMMON_SOURCE="${BASH_SOURCE[0]:-$0}"
fi

SCRIPT_DIR="$(cd "$(dirname "$_COMMON_SOURCE")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

load_project_env() {
  set -a
  [[ -f "$ROOT/project.env" ]] && source "$ROOT/project.env"
  [[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
  set +a
}

python_bin() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    printf '%s\n' "$ROOT/.venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}

ensure_recipients_file() {
  if [[ ! -f "$ROOT/email_recipients.txt" && -f "$ROOT/email_recipients.example.txt" ]]; then
    cp "$ROOT/email_recipients.example.txt" "$ROOT/email_recipients.txt"
  fi
}
