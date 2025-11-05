#!/usr/bin/env bash
set -euo pipefail

ENV_DIR=".venv-py311"

if [[ ! -x "$(command -v python3.11)" ]]; then
  echo "python3.11 is required but not found on PATH." >&2
  exit 1
fi

if [[ ! -d "${ENV_DIR}" ]]; then
  python3.11 -m venv "${ENV_DIR}"
fi

source "${ENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install --upgrade wheel setuptools

python -m pip install -r requirements/base.txt
python -m pip install -r requirements/dev.txt

python -m pip install crewai langchain-ollama

cat <<SETUP
================================================================
Python 3.11 environment ready at ${ENV_DIR}
Activate with:  source ${ENV_DIR}/bin/activate
================================================================
SETUP
