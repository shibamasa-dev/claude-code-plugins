#!/bin/bash
# Shared helpers for test-*.sh. Every call goes through the MCP server over stdio (tests/mcp_call.py).
#
# SQLite by default: each fresh_db gets a new temporary CLAUDE_PLUGIN_DATA.
# Postgres when INVENTORY_PG_ADMIN_URL is set (run-postgres.sh does that): each fresh_db creates a new database.
TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CALL="$TESTS/mcp_call.py"
FIXTURES="$TESTS/fixtures"

fresh_db() {
  unset INVENTORY_SQLITE_PATH INVENTORY_ROUTE
  if [ -n "${INVENTORY_PG_ADMIN_URL:-}" ]; then
    local name="inv_test_$$_$RANDOM"
    psql "$INVENTORY_PG_ADMIN_URL" -X -q -c "CREATE DATABASE $name" >/dev/null || exit 1
    export INVENTORY_DATABASE_URL="${INVENTORY_PG_ADMIN_URL%/*}/$name"
    unset CLAUDE_PLUGIN_DATA
  else
    unset INVENTORY_DATABASE_URL
    CLAUDE_PLUGIN_DATA="$(mktemp -d "${TMPDIR:-/tmp}/inventory-test.XXXXXX")"
    export CLAUDE_PLUGIN_DATA
  fi
}
is_postgres() { [ -n "${INVENTORY_PG_ADMIN_URL:-}" ]; }

# sql STATEMENT...: one execute_sql call each, one result line each
sql() { python3 "$CALL" "$@"; }
# val STATEMENT: the first column of the first row
val() { python3 "$CALL" --value "$1"; }
load_fixtures() { python3 "$CALL" --file "$FIXTURES/items.sql" >/dev/null; }

# yesno CONDITION...: run the test command and print yes or no
yesno() { if "$@"; then echo yes; else echo no; fi; }
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }
