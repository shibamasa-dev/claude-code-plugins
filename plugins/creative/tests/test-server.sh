#!/bin/bash
# The MCP server itself: its tools, where it puts the data, and that it never switches stores on its own.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
row 'tools/list offers exactly execute_sql and apply_migrations' "$(yesno [ "$(python3 "$CALL" --list)" = execute_sql,apply_migrations ])" 'yes'
out=$(CREATIVE_HISTORY_ROUTE=connector sql "SELECT 1")
row 'with route=connector every call is refused and points at the connector' "$(yesno grep -q "^ERROR: .*route is 'connector'" <<<"$out")" 'yes'

if is_postgres; then
  bad=$(CREATIVE_HISTORY_DATABASE_URL="${CREATIVE_HISTORY_DATABASE_URL%/*}/no_such_db" sql "SELECT 1")
  row 'a database_url that fails is an error, not a fallback to SQLite' "$(yesno grep -q '^ERROR' <<<"$bad")" 'yes'
  echo '  (SQLite path rows skipped on Postgres)'
  exit 0
fi

# A fresh install: HOME, the working directory and the data directory are all new and empty.
# After the first call, every new file must be inside CLAUDE_PLUGIN_DATA.
root=$(mktemp -d "${TMPDIR:-/tmp}/creative-fresh.XXXXXX")
mkdir -p "$root/home" "$root/cwd" "$root/data/creative-shibamasa-plugins"
(cd "$root/cwd" && HOME="$root/home" CLAUDE_PLUGIN_DATA="$root/data/creative-shibamasa-plugins" python3 "$CALL" "SELECT 1") >/dev/null
row 'a fresh install creates image-history/history.sqlite3 in the plugin data directory' "$(yesno [ -f "$root/data/creative-shibamasa-plugins/image-history/history.sqlite3" ])" 'yes'
outside=$(cd "$root" && find home cwd -type f | wc -l | tr -d ' ')
row 'files written outside the plugin data directory' "$outside" '0'

sql "SELECT 1" >/dev/null
CREATIVE_HISTORY_SQLITE_PATH="$CLAUDE_PLUGIN_DATA/elsewhere/my.db" sql "SELECT 1" >/dev/null
row 'sqlite_path moves the file' "$(yesno [ -f "$CLAUDE_PLUGIN_DATA/elsewhere/my.db" ])" 'yes'
# An option the user never set may reach the server as the literal placeholder
out=$(CREATIVE_HISTORY_DATABASE_URL='${user_config.database_url}' python3 "$CALL" --tool apply_migrations)
row 'an unexpanded ${user_config.database_url} counts as unset' "$(yesno grep -q '"backend": "sqlite"' <<<"$out")" 'yes'
out=$(CREATIVE_HISTORY_DATABASE_URL='postgresql://127.0.0.1:1/none' sql "SELECT 1")
row 'a database_url that fails is an error, not a fallback to SQLite' "$(yesno grep -q '^ERROR' <<<"$out")" 'yes'
rm -rf "$root"
