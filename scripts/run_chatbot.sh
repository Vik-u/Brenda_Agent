#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"<question>\" [--show-sql]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/.."

if [[ -d "${REPO_ROOT}/.venv-py311" ]]; then
  source "${REPO_ROOT}/.venv-py311/bin/activate"
elif [[ -d "${REPO_ROOT}/.venv" ]]; then
  source "${REPO_ROOT}/.venv/bin/activate"
else
  echo "No virtual environment found. Run scripts/setup_py311_env.sh first." >&2
  exit 1
fi

cd "${REPO_ROOT}"
python -m src.interfaces.chatbot_cli "$@"
