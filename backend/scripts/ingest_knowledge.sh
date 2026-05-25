#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ../scripts/env.local.sh
export PYTHONPATH="$PWD"
python -m app.rag.knowledge_ingest
