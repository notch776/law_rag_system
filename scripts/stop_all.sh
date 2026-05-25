#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.local.sh"

stop_pid() {
  local name="$1" file="$2"
  if [ -f "$file" ]; then
    local pid
    pid="$(cat "$file")"
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "Stopping $name pid=$pid"
      kill "$pid" || true
    fi
    rm -f "$file"
  fi
}

stop_pid Backend "$PROJECT_ROOT/.local/pids/backend.pid"
stop_pid Frontend "$PROJECT_ROOT/.local/pids/frontend.pid"
"$PROJECT_ROOT/scripts/stop_dbs.sh"
