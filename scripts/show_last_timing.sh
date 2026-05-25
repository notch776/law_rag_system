#!/usr/bin/env bash
set -euo pipefail
LOG_FILE="${1:-/Users/bytedance/final_project/.local/logs/backend.log}"
if [ ! -f "$LOG_FILE" ]; then
  echo "log file not found: $LOG_FILE" >&2
  exit 1
fi
last_trace=$(grep 'QA_TIMING' "$LOG_FILE" 2>/dev/null | sed -E 's/.*trace=([^ ]+).*/\1/' | tail -n 1 || true)
if [ -z "${last_trace:-}" ]; then
  echo '没有找到 QA_TIMING 日志。请先发起一次问答。'
  exit 0
fi
printf 'trace=%s\n' "$last_trace"
grep "QA_TIMING trace=$last_trace" "$LOG_FILE" | sed -E 's/^.*stage=([^ ]+) delta_ms=([0-9.]+) total_ms=([0-9.]+)(.*)$/stage=\1\tdelta_ms=\2\ttotal_ms=\3\4/'
