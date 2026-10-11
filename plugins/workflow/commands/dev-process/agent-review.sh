#!/bin/bash
# Script that runs reviews in parallel
# Runs reviews by multiple agents at once and prints the results once both finish
# Usage: ./agent-review.sh [title]

set -e

# ================================
# Debug settings
# ================================
DEBUG_MODE=true  # true to write debug logs
LOG_DIR="logs"
LOG_FILE="${LOG_DIR}/agent-review-$(date +%Y%m%d).log"

# Create the log directory
mkdir -p "$LOG_DIR"

# Debug log function
debug_log() {
  if [ "$DEBUG_MODE" = true ]; then
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [DEBUG] $*" >> "$LOG_FILE"
  fi
}

# Error log function
error_log() {
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$timestamp] [ERROR] $*" >> "$LOG_FILE"
  echo "[$timestamp] [ERROR] $*" >&2
}

debug_log "=========================================="
debug_log "Script start: $0"
debug_log "Args: $*"
debug_log "Current directory: $(pwd)"
debug_log "=========================================="

mkdir -p .context/review

# Timestamp
TIMESTAMP=$(date +%Y%m%d%H%M%S)
debug_log "Timestamp: $TIMESTAMP"

# Title (used if given as an argument)
TITLE="$1"
if [ -n "$TITLE" ]; then
  SUFFIX="_${TITLE}"
  debug_log "Title given: $TITLE"
else
  SUFFIX=""
  debug_log "No title given"
fi

CODEX_FILE=".context/review/${TIMESTAMP}_review${SUFFIX}_by_codex.md"
CODERABBIT_FILE=".context/review/${TIMESTAMP}_review${SUFFIX}_by_coderabbit.md"
debug_log "Codex output file: $CODEX_FILE"
debug_log "CodeRabbit output file: $CODERABBIT_FILE"

# Codex review (runs in the background)
debug_log "Starting Codex review..."
debug_log "Codex command: codex exec '/review' --output-last-message $CODEX_FILE"
codex exec '/review' --output-last-message "$CODEX_FILE" > /dev/null 2>&1 &
PID1=$!
debug_log "Codex PID: $PID1"

# CodeRabbit review (runs in the background)
debug_log "Starting CodeRabbit review..."
debug_log "CodeRabbit command: coderabbit --plain --type uncommitted > $CODERABBIT_FILE"
coderabbit --plain --type uncommitted > "$CODERABBIT_FILE" 2>&1 &
PID2=$!
debug_log "CodeRabbit PID: $PID2"

# Wait for both to finish (keep going even on a non-zero exit)
debug_log "Waiting for both processes to finish (PID: $PID1, $PID2)"
set +e
wait $PID1
CODEX_EXIT=$?
set -e
debug_log "Codex exit code: $CODEX_EXIT"

set +e
wait $PID2
CODERABBIT_EXIT=$?
set -e
debug_log "CodeRabbit exit code: $CODERABBIT_EXIT"

# Check the files exist (exit early if not)
HAS_ERROR=false
if [ -f "$CODEX_FILE" ]; then
  debug_log "Codex file exists: OK ($(wc -c < "$CODEX_FILE") bytes)"
else
  error_log "Codex file does not exist: $CODEX_FILE (exit code: $CODEX_EXIT)"
  HAS_ERROR=true
fi

if [ -f "$CODERABBIT_FILE" ]; then
  debug_log "CodeRabbit file exists: OK ($(wc -c < "$CODERABBIT_FILE") bytes)"
else
  error_log "CodeRabbit file does not exist: $CODERABBIT_FILE (exit code: $CODERABBIT_EXIT)"
  HAS_ERROR=true
fi

if [ "$HAS_ERROR" = true ]; then
  error_log "Failed to generate the review files"
  exit 1
fi

# Print the results
debug_log "Printing results"
echo "✅ All reviews are done!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Codex Review"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat "$CODEX_FILE"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐰 CodeRabbit Review"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat "$CODERABBIT_FILE"

debug_log "Script finished normally"
debug_log "=========================================="
