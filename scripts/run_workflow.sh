#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <ec_number> [organism]"
  exit 1
fi

ec_number=$1
organism=${2:-}

source .venv/bin/activate
python -m src.main "$ec_number" ${organism:+--organism "$organism"}
