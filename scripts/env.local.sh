#!/usr/bin/env bash
# Unified local environment for refined legal RAG system.
# Source this file before running backend scripts: source scripts/env.local.sh

export PROJECT_ROOT="/Users/bytedance/final_project"
export BACKEND_DIR="$PROJECT_ROOT/backend"
export FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Load project env files. backend/rag/.env is loaded last so the real API key there wins over placeholders.
# The parser tolerates legacy lines like "INDEX_NAME = new_qiyefa".
load_env_file() {
  local file="$1"
  [ -f "$file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -z "$line" ] && continue
    [[ "$line" != *=* ]] && continue
    local key=""
    local value=""
    key="$(printf '%s' "${line%%=*}" | sed -E 's/[[:space:]]+$//')"
    value="$(printf '%s' "${line#*=}" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    value="${value%\"}"
    value="${value#\"}"
    export "$key=$value"
  done < "$file"
}

load_env_file "$PROJECT_ROOT/.env"
load_env_file "$BACKEND_DIR/.env"
load_env_file "$BACKEND_DIR/rag/.env"

export APP_ENV="${APP_ENV:-local}"
export DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-}"
export LLM_MODEL="${LLM_MODEL:-qwen3.6-max-preview}"
export SMALL_LLM_MODEL="${SMALL_LLM_MODEL:-qwen3.6-flash}"
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-tongyi-embedding-vision-plus-2026-03-06}"

export ES_HOST="${ES_HOST:-http://localhost:9200}"
export ES_INDEX="${ES_INDEX:-${INDEX_NAME:-new_qiyefa}}"
export INDEX_NAME="$ES_INDEX"
export DOCS_FOLDER="$BACKEND_DIR/rag/data"

export MONGODB_URL="${MONGODB_URL:-mongodb://localhost:27017}"
export MONGODB_DATABASE="${MONGODB_DATABASE:-${DATABASE_NAME:-rag_system}}"
export DATABASE_NAME="$MONGODB_DATABASE"
export CONVERSATIONS_COLLECTION="${CONVERSATIONS_COLLECTION:-${COLLECTION_NAME:-chat_history}}"
export COLLECTION_NAME="$CONVERSATIONS_COLLECTION"
export SUMMARIES_COLLECTION="${SUMMARIES_COLLECTION:-conversation_summaries}"

export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export REDIS_DB="${REDIS_DB:-0}"

export NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
export NEO4J_AUTH="${NEO4J_AUTH:-neo4j/Gl20031010}"
export LONG_MEMORY_CATEGORY_THRESHOLD="${LONG_MEMORY_CATEGORY_THRESHOLD:-0.8}"
export LONG_MEMORY_DOC_THRESHOLD="${LONG_MEMORY_DOC_THRESHOLD:-0.9}"

export RERANK_PROVIDER="${RERANK_PROVIDER:-dashscope}"
export RERANK_MODEL_NAME="${RERANK_MODEL_NAME:-qwen3-rerank}"
export RERANK_ENDPOINT="${RERANK_ENDPOINT:-https://dashscope.aliyuncs.com/compatible-api/v1/reranks}"
export RERANK_MODEL_PATH="${RERANK_MODEL_PATH:-$BACKEND_DIR/rag/rerank_model}"
export RERANK_ENABLED="${RERANK_ENABLED:-true}"
export FUSION_TOP_K="${FUSION_TOP_K:-10}"
export RERANK_TOP_N="${RERANK_TOP_N:-5}"
export DOCS_PER_INTENT="${DOCS_PER_INTENT:-5}"
export SHORT_MEMORY_WINDOW="${SHORT_MEMORY_WINDOW:-5}"
export SHORT_MEMORY_TTL_SECONDS="${SHORT_MEMORY_TTL_SECONDS:-3600}"
export SUMMARY_INTERVAL="${SUMMARY_INTERVAL:-6}"

export PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}"
