#!/bin/bash
# Measures design-lint.py offline: silent for files other than DESIGN.md, and loud (not silent) when lint cannot run.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/design-lint.py"
TMP=$(mktemp -d) || exit 1; trap 'rm -rf "$TMP"' EXIT
printf '# Design\n' > "$TMP/DESIGN.md"; printf '# Readme\n' > "$TMP/README.md"
PY=$(python3 -c 'import sys; print(sys.executable)')  # the real interpreter, so an empty PATH still runs the hook
NONPX="$TMP/bin"; mkdir "$NONPX"

# run <tool> <path> [PATH]: none if the output is empty, notrun if it says lint was not run, other otherwise
run() {
  out=$(printf '{"hook_event_name":"PostToolUse","tool_name":"%s","tool_input":{"file_path":"%s"}}' "$1" "$2" \
    | PATH="${3:-$PATH}" "$PY" "$HOOK")
  case "$out" in
    '') echo none ;;
    *additionalContext*'lint NOT RUN'*) echo notrun ;;
    *) echo other ;;
  esac
}
row() { printf '  %-58s -> %-6s (expect %s)\n' "$1" "$2" "$3"; }

echo '=== target filter ==='
row 'silent for a file other than DESIGN.md' "$(run Edit "$TMP/README.md")" 'none'
row 'silent for a DESIGN.md that does not exist' "$(run Write "$TMP/missing/DESIGN.md")" 'none'
row 'silent for a tool other than Edit or Write' "$(run Read "$TMP/DESIGN.md")" 'none'
echo '=== lint cannot run ==='
row 'says lint was not run when npx is missing' "$(run Edit "$TMP/DESIGN.md" "$NONPX")" 'notrun'
