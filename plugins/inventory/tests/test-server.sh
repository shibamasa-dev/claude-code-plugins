#!/bin/bash
# The MCP server itself: its tools, where it puts the data, and that it never switches stores on its own.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
row 'tools/list offers exactly execute_sql and apply_migrations' "$(yesno [ "$(python3 "$CALL" --list)" = execute_sql,apply_migrations ])" 'yes'
out=$(INVENTORY_ROUTE=connector sql "SELECT 1")
row 'with route=connector every call is refused and points at the connector' "$(yesno grep -q "^ERROR: .*route is 'connector'" <<<"$out")" 'yes'

if is_postgres; then
  bad=$(INVENTORY_DATABASE_URL="${INVENTORY_DATABASE_URL%/*}/no_such_db" sql "SELECT 1")
  row 'a database_url that fails is an error, not a fallback to SQLite' "$(yesno grep -q '^ERROR' <<<"$bad")" 'yes'
  echo '  (SQLite path rows skipped on Postgres)'
  exit 0
fi

sql "SELECT 1" >/dev/null
row 'by default the SQLite file is inventory.sqlite3 in the plugin data directory' "$(yesno [ -f "$CLAUDE_PLUGIN_DATA/inventory.sqlite3" ])" 'yes'
INVENTORY_SQLITE_PATH="$CLAUDE_PLUGIN_DATA/elsewhere/my.db" sql "SELECT 1" >/dev/null
row 'sqlite_path moves the file' "$(yesno [ -f "$CLAUDE_PLUGIN_DATA/elsewhere/my.db" ])" 'yes'
# An option the user never set may reach the server as the literal placeholder
out=$(INVENTORY_DATABASE_URL='${user_config.database_url}' python3 "$CALL" --tool apply_migrations)
row 'an unexpanded ${user_config.database_url} counts as unset' "$(yesno grep -q '"backend": "sqlite"' <<<"$out")" 'yes'
out=$(INVENTORY_DATABASE_URL='postgresql://127.0.0.1:1/none' sql "SELECT 1")
row 'a database_url that fails is an error, not a fallback to SQLite' "$(yesno grep -q '^ERROR' <<<"$out")" 'yes'
