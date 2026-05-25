#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.local.sh"

"$PROJECT_ROOT/scripts/start_dbs.sh"

mkdir -p "$PROJECT_ROOT/.local/logs" "$PROJECT_ROOT/.local/pids"

if ! lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo 'Starting backend on http://localhost:8000 ...'
  nohup "$PROJECT_ROOT/scripts/start_backend.sh" > "$PROJECT_ROOT/.local/logs/backend.log" 2>&1 &
  echo $! > "$PROJECT_ROOT/.local/pids/backend.pid"
else
  echo 'Backend already running on 8000'
fi

if ! lsof -nP -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo 'Starting frontend on http://localhost:5173 ...'
  nohup "$PROJECT_ROOT/scripts/start_frontend.sh" > "$PROJECT_ROOT/.local/logs/frontend.log" 2>&1 &
  echo $! > "$PROJECT_ROOT/.local/pids/frontend.pid"
else
  echo 'Frontend already running on 5173'
fi

sleep 5
"$PROJECT_ROOT/scripts/check_services.sh"
if command -v curl >/dev/null 2>&1; then
  echo 'Backend health:'
  curl -fsS http://localhost:8000/health || true
  echo
fi

echo 'Frontend URL: http://localhost:5173/'
echo 'Backend URL:  http://localhost:8000/'
echo 'Logs: .local/logs/backend.log, .local/logs/frontend.log, .local/logs/*.log'
