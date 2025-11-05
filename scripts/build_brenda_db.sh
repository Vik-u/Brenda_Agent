#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}/.."

RAW_JSON="${1:-${REPO_ROOT}/data/raw/brenda_2025_1.json}"
RAW_TXT="${2:-${REPO_ROOT}/data/raw/brenda_2025_1.txt}"
TARGET_DB="${3:-${REPO_ROOT}/data/processed/brenda.db}"

if [[ ! -f "${RAW_JSON}" ]]; then
  echo "Missing JSON dump: ${RAW_JSON}" >&2
  echo "Download or extract the BRENDA JSON release into data/raw/ and rerun." >&2
  exit 1
fi

if [[ ! -f "${RAW_TXT}" ]]; then
  echo "Missing TXT dump: ${RAW_TXT}" >&2
  echo "Download or extract the BRENDA TXT release into data/raw/ and rerun." >&2
  exit 1
fi

if [[ -d "${REPO_ROOT}/.venv-py311" ]]; then
  source "${REPO_ROOT}/.venv-py311/bin/activate"
elif [[ -d "${REPO_ROOT}/.venv" ]]; then
  source "${REPO_ROOT}/.venv/bin/activate"
else
  echo "No virtual environment found. Run scripts/setup_py311_env.sh first." >&2
  exit 1
fi

mkdir -p "$(dirname "${TARGET_DB}")"

python -m src.pipelines.brenda_ingestion \
  --source "${RAW_JSON}" \
  --text "${RAW_TXT}" \
  --target "${TARGET_DB}"

echo "Built database at ${TARGET_DB}"
