#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.local.sh"

mkdir -p "$PROJECT_ROOT/.local/logs" "$PROJECT_ROOT/.local/pids" \
  "$PROJECT_ROOT/.local/mongodb-data" "$PROJECT_ROOT/.local/redis" "$PROJECT_ROOT/.local/elasticsearch-data"

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
is_port_open() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
wait_port() {
  local port="$1" name="$2" retries="${3:-60}"
  for _ in $(seq 1 "$retries"); do
    if is_port_open "$port"; then log "$name ready on port $port"; return 0; fi
    sleep 1
  done
  log "$name did not become ready on port $port"
  return 1
}

start_mongodb() {
  if is_port_open 27017; then log 'MongoDB already running on 27017'; return; fi
  local mongod="$PROJECT_ROOT/.local/mongodb/bin/mongod"
  if [ ! -x "$mongod" ]; then
    mongod="$(command -v mongod || true)"
  fi
  if [ -z "$mongod" ]; then
    log 'MongoDB binary not found. Expected .local/mongodb/bin/mongod or PATH mongod.'
    return 1
  fi
  log 'Starting MongoDB locally...'
  nohup "$mongod" --dbpath "$PROJECT_ROOT/.local/mongodb-data" --bind_ip 127.0.0.1 --port 27017 \
    > "$PROJECT_ROOT/.local/logs/mongodb.log" 2>&1 &
  echo $! > "$PROJECT_ROOT/.local/pids/mongodb.pid"
  wait_port 27017 MongoDB 60
}

start_redis() {
  if is_port_open "$REDIS_PORT"; then log "Redis already running on $REDIS_PORT"; return; fi
  local redis_bin="$(command -v redis-server || true)"
  [ -z "$redis_bin" ] && [ -x /opt/homebrew/opt/redis/bin/redis-server ] && redis_bin=/opt/homebrew/opt/redis/bin/redis-server
  if [ -z "$redis_bin" ]; then log 'redis-server not found. Install redis with Homebrew first.'; return 1; fi
  log 'Starting Redis locally...'
  nohup "$redis_bin" --port "$REDIS_PORT" --dir "$PROJECT_ROOT/.local/redis" --daemonize no \
    > "$PROJECT_ROOT/.local/logs/redis.log" 2>&1 &
  echo $! > "$PROJECT_ROOT/.local/pids/redis.pid"
  wait_port "$REDIS_PORT" Redis 30
}

start_neo4j() {
  if is_port_open 7687; then log 'Neo4j already running on 7687'; return; fi
  local neo4j_bin="$(command -v neo4j || true)"
  [ -z "$neo4j_bin" ] && [ -x /opt/homebrew/opt/neo4j/bin/neo4j ] && neo4j_bin=/opt/homebrew/opt/neo4j/bin/neo4j
  if [ -z "$neo4j_bin" ]; then log 'neo4j not found. Install neo4j with Homebrew first.'; return 1; fi
  log 'Starting Neo4j locally...'
  nohup "$neo4j_bin" console > "$PROJECT_ROOT/.local/logs/neo4j.log" 2>&1 &
  echo $! > "$PROJECT_ROOT/.local/pids/neo4j.pid"
  wait_port 7687 Neo4j 90
}

start_elasticsearch() {
  if is_port_open 9200; then log 'Elasticsearch already running on 9200'; return; fi
  if ! command -v docker >/dev/null 2>&1; then
    log 'Elasticsearch binary not found and Docker is unavailable. Install ES locally or start your existing ES container.'
    return 1
  fi
  if docker inspect es-ragchat >/dev/null 2>&1; then
    log 'Starting existing Elasticsearch container es-ragchat...'
    docker start es-ragchat >/dev/null
  else
    log 'Creating and starting Elasticsearch container es-ragchat...'
    docker run -d --name es-ragchat \
      -p 9200:9200 \
      -e discovery.type=single-node \
      -e xpack.security.enabled=false \
      -e ES_JAVA_OPTS='-Xms2g -Xmx2g' \
      -v es-ragchat-data:/usr/share/elasticsearch/data \
      docker.elastic.co/elasticsearch/elasticsearch:8.10.4 >/dev/null
  fi
  wait_port 9200 Elasticsearch 120
}

start_mongodb
start_redis
start_neo4j
start_elasticsearch

log 'Database services started.'
"$(dirname "$0")/check_services.sh"
