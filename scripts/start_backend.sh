#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.local.sh"
cd "$BACKEND_DIR"

UVICORN_BIN="$PROJECT_ROOT/final_project/bin/uvicorn"
if [ ! -x "$UVICORN_BIN" ]; then
  UVICORN_BIN="$(command -v uvicorn)"
fi

exec "$UVICORN_BIN" main:app --host 0.0.0.0 --port 8000
