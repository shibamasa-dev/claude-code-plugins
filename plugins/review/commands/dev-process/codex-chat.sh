#!/bin/bash
# Codex対話スクリプト
# Usage: ./codex-chat.sh "プロンプト"

PROMPT="$1"
if [ -z "$PROMPT" ]; then
  echo "Usage: $(basename "$0") \"プロンプト\""
  exit 1
fi

mkdir -p .context/codex
TIMESTAMP=$(date +%Y%m%d%H%M%S)
OUTPUT_FILE=".context/codex/${TIMESTAMP}_codex.md"

codex exec "$PROMPT" --output-last-message "$OUTPUT_FILE" > /dev/null 2>&1 &
PID=$!
wait $PID

cat "$OUTPUT_FILE"
