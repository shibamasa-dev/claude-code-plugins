#!/bin/bash
# Script that runs reviews in parallel
# Runs reviews by multiple agents at once and prints the results once both finish
# Usage: ./agent-review.sh [title]

set -e

# ================================
# Debug settings
# ================================
DEBUG_MODE=true  # true to write debug logs
# Reports and logs are read again later, so they go to .context/workflow/ (the repo's "Where plugins write" rule),
# kept out of git through .git/info/exclude rather than the tracked .gitignore
OUT_DIR=".context/workflow"
LOG_DIR="${OUT_DIR}/logs"
LOG_FILE="${LOG_DIR}/agent-review-$(date +%Y%m%d).log"

# Create the output directories and exclude .context/ (once; skipped outside a git repo)
mkdir -p "$LOG_DIR" "${OUT_DIR}/review"
if EXCLUDE=$(git rev-parse --git-path info/exclude 2>/dev/null); then
  mkdir -p "$(dirname "$EXCLUDE")"
  if ! grep -qxF '.context/' "$EXCLUDE" 2>/dev/null; then
    [ -s "$EXCLUDE" ] && [ -n "$(tail -c1 "$EXCLUDE")" ] && echo >> "$EXCLUDE"   # the last line has no newline
    echo '.context/' >> "$EXCLUDE"
  fi
fi

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

CODEX_FILE="${OUT_DIR}/review/${TIMESTAMP}_review${SUFFIX}_by_codex.md"
CODERABBIT_FILE="${OUT_DIR}/review/${TIMESTAMP}_review${SUFFIX}_by_coderabbit.md"
# Codex writes only its last message to CODEX_FILE; its console output (where an error goes) is kept here
CODEX_LOG="${LOG_DIR}/${TIMESTAMP}_codex${SUFFIX}.log"
debug_log "Codex output file: $CODEX_FILE"
debug_log "CodeRabbit output file: $CODERABBIT_FILE"

# Codex review (runs in the background)
debug_log "Starting Codex review..."
debug_log "Codex command: codex exec '/review' --output-last-message $CODEX_FILE > $CODEX_LOG"
codex exec '/review' --output-last-message "$CODEX_FILE" > "$CODEX_LOG" 2>&1 &
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

# A reviewer failed when it exited non-zero or left no output file. What it printed then is an error, not review
# findings (CodeRabbit's file holds its stderr; Codex's is in CODEX_LOG), so it goes under a FAILED line and the script exits 1
FAILED=""
# failure_reason <exit code> <file> -> prints why the run failed and returns 0, or returns 1 when it succeeded
failure_reason() {
  if [ "$1" -ne 0 ]; then echo "exit $1"
  elif [ ! -f "$2" ]; then echo "no output file"
  else return 1; fi
}
for r in Codex CodeRabbit; do
  if [ "$r" = Codex ]; then rc=$CODEX_EXIT; f=$CODEX_FILE; else rc=$CODERABBIT_EXIT; f=$CODERABBIT_FILE; fi
  if why=$(failure_reason "$rc" "$f"); then
    error_log "$r review failed ($why): $f"
    FAILED="${FAILED:+$FAILED, }$r ($why)"
  else
    debug_log "$r file exists: OK ($(wc -c < "$f") bytes)"
  fi
done

# section <icon> <name> <exit code> <file> [console log]: prints one reviewer's findings, or its error under a FAILED line
# (the output file, else the last 20 lines of the console log)
section() {
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  if why=$(failure_reason "$3" "$4"); then
    echo "❌ $2 review FAILED ($why)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Error output, not review findings:"
    if [ -s "$4" ]; then cat "$4"
    elif [ -s "${5:-}" ]; then echo "(last lines of $5)"; tail -n 20 "$5"
    else echo "(no output)"; fi
  else
    echo "$1 $2 Review"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    cat "$4"
  fi
}

# Print the results
debug_log "Printing results"
if [ -z "$FAILED" ]; then
  echo "✅ All reviews are done!"
else
  echo "❌ Review failed: $FAILED. The failed output below is an error, not review findings."
fi
echo ""
section "📋" Codex "$CODEX_EXIT" "$CODEX_FILE" "$CODEX_LOG"
echo ""
section "🐰" CodeRabbit "$CODERABBIT_EXIT" "$CODERABBIT_FILE"

if [ -n "$FAILED" ]; then
  debug_log "Script finished with failed reviews: $FAILED"
  debug_log "=========================================="
  exit 1
fi
debug_log "Script finished normally"
debug_log "=========================================="
