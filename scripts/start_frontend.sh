#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.local.sh"
cd "$FRONTEND_DIR"
exec npm run dev -- --host 0.0.0.0
