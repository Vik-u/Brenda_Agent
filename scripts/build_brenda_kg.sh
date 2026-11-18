#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/.."

SOURCE_DB="${1:-${REPO_ROOT}/data/processed/brenda.db}"
TARGET_DB="${2:-${REPO_ROOT}/data/processed/brenda_kg.db}"

if [[ -d "${REPO_ROOT}/.venv-py311" ]]; then
  source "${REPO_ROOT}/.venv-py311/bin/activate"
elif [[ -d "${REPO_ROOT}/.venv" ]]; then
  source "${REPO_ROOT}/.venv/bin/activate"
else
  echo "No virtual environment found. Run scripts/setup_py311_env.sh first." >&2
  exit 1
fi

python -m src.pipelines.brenda_kg_builder \
  --source "${SOURCE_DB}" \
  --target "${TARGET_DB}" \
  --include-text

echo "Built KG at ${TARGET_DB}"
