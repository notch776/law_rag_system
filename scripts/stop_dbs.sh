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

stop_pid MongoDB "$PROJECT_ROOT/.local/pids/mongodb.pid"
stop_pid Redis "$PROJECT_ROOT/.local/pids/redis.pid"
stop_pid Neo4j "$PROJECT_ROOT/.local/pids/neo4j.pid"

if command -v docker >/dev/null 2>&1 && docker inspect es-ragchat >/dev/null 2>&1; then
  echo 'Stopping Elasticsearch container es-ragchat'
  docker stop es-ragchat >/dev/null || true
fi
