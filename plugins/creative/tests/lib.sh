#!/bin/bash
# Shared helpers for test-*.sh. Database calls go through the MCP server over stdio (tests/mcp_call.py).
#
# SQLite by default: each fresh_db gets a new temporary CLAUDE_PLUGIN_DATA (named like the plugin's own directory).
# Postgres when CREATIVE_HISTORY_PG_ADMIN_URL is set (run-postgres.sh does that): each fresh_db creates a new database.
TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALL="$TESTS/mcp_call.py"
FIXTURES="$TESTS/fixtures"
HISTORY="$TESTS/../skills/image-generation-prompt/scripts/history.py"

fresh_db() {
  unset CREATIVE_HISTORY_SQLITE_PATH CREATIVE_HISTORY_ROUTE
  if [ -n "${CREATIVE_HISTORY_PG_ADMIN_URL:-}" ]; then
    local name="img_test_$$_$RANDOM"
    psql "$CREATIVE_HISTORY_PG_ADMIN_URL" -X -q -c "CREATE DATABASE $name" >/dev/null || exit 1
    export CREATIVE_HISTORY_DATABASE_URL="${CREATIVE_HISTORY_PG_ADMIN_URL%/*}/$name"
    unset CLAUDE_PLUGIN_DATA
  else
    unset CREATIVE_HISTORY_DATABASE_URL
    fresh_data
  fi
}
# fresh_data: a new empty CLAUDE_PLUGIN_DATA whose name matches the plugin's own directory
fresh_data() {
  CLAUDE_PLUGIN_DATA="$(mktemp -d "${TMPDIR:-/tmp}/creative-test.XXXXXX")/creative-shibamasa-plugins"
  mkdir -p "$CLAUDE_PLUGIN_DATA"
  export CLAUDE_PLUGIN_DATA
}
is_postgres() { [ -n "${CREATIVE_HISTORY_PG_ADMIN_URL:-}" ]; }

# sql STATEMENT...: one execute_sql call each, one result line each
sql() { python3 "$CALL" "$@"; }
# val STATEMENT: the first column of the first row
val() { python3 "$CALL" --value "$1"; }
load_fixtures() { python3 "$CALL" --file "$FIXTURES/history.sql" >/dev/null; }

# yesno CONDITION...: run the test command and print yes or no
yesno() { if "$@"; then echo yes; else echo no; fi; }
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }
