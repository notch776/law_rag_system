#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.local.sh"

check_port() {
  local name="$1" port="$2"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'OK   %-15s port %s\n' "$name" "$port"
  else
    printf 'MISS %-15s port %s\n' "$name" "$port"
  fi
}

check_port MongoDB 27017
check_port Redis "$REDIS_PORT"
check_port Neo4j-Bolt 7687
check_port Neo4j-HTTP 7474
check_port Elasticsearch 9200

if command -v curl >/dev/null 2>&1 && curl -fsS "$ES_HOST/_cluster/health" >/tmp/es-health.json 2>/dev/null; then
  printf 'OK   Elasticsearch health: '
  cat /tmp/es-health.json
  printf '\n'
fi
