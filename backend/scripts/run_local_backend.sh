#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ../scripts/env.local.sh
export PYTHONPATH="$PWD"
uvicorn main:app --host 0.0.0.0 --port 8000
