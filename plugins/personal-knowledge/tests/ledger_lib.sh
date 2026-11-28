#!/bin/bash
# Shared helpers for test-ledger-*.sh. Database calls go through the ledger MCP server over stdio (ledger_mcp_call.py).
#
# SQLite by default: each fresh_db gets a new temporary CLAUDE_PLUGIN_DATA (named like the plugin's own directory).
# Postgres when LEDGER_PG_ADMIN_URL is set (run-postgres.sh does that): each fresh_db creates a new database.
TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALL="$TESTS/ledger_mcp_call.py"
FIXTURES="$TESTS/fixtures"

fresh_db() {
  unset LEDGER_SQLITE_PATH LEDGER_ROUTE
  if [ -n "${LEDGER_PG_ADMIN_URL:-}" ]; then
    local name="rl_test_$$_$RANDOM"
    psql "$LEDGER_PG_ADMIN_URL" -X -q -c "CREATE DATABASE $name" >/dev/null || exit 1
    export LEDGER_DATABASE_URL="${LEDGER_PG_ADMIN_URL%/*}/$name"
    unset CLAUDE_PLUGIN_DATA
  else
    unset LEDGER_DATABASE_URL
    fresh_data
  fi
}
# fresh_data: a new empty CLAUDE_PLUGIN_DATA whose name matches the plugin's own directory
fresh_data() {
  CLAUDE_PLUGIN_DATA="$(mktemp -d "${TMPDIR:-/tmp}/personal-knowledge-test.XXXXXX")/personal-knowledge-shibamasa-plugins"
  mkdir -p "$CLAUDE_PLUGIN_DATA"
  export CLAUDE_PLUGIN_DATA
}
is_postgres() { [ -n "${LEDGER_PG_ADMIN_URL:-}" ]; }

# sql STATEMENT...: one execute_sql call each, one result line each
sql() { python3 "$CALL" "$@"; }
# val STATEMENT: the first column of the first row
val() { python3 "$CALL" --value "$1"; }
load_fixtures() { python3 "$CALL" --file "$FIXTURES/ledger.sql" >/dev/null; }
# rejected STATEMENT: yes when the statement comes back as a tool error
rejected() { yesno grep -q '^ERROR' <<<"$(sql "$1")"; }

# yesno CONDITION...: run the test command and print yes or no
yesno() { if "$@"; then echo yes; else echo no; fi; }
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }
