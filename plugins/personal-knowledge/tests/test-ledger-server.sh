#!/bin/bash
# relationship-ledger's MCP server: its tools, where it puts the data, and that it never switches stores on its own.
set -u
. "$(dirname "$0")/ledger_lib.sh"

fresh_db
row 'tools/list offers exactly execute_sql and apply_migrations' "$(yesno [ "$(python3 "$CALL" --list)" = execute_sql,apply_migrations ])" 'yes'
out=$(LEDGER_ROUTE=connector sql "SELECT 1")
row 'with ledger_route=connector every call is refused and points at the connector' "$(yesno grep -q "^ERROR: .*ledger_route is 'connector'" <<<"$out")" 'yes'

# Rows that need psycopg (uv downloads it) run only on the Postgres runner, so run-all.sh stays offline
if is_postgres; then
  # psycopg's errors quote the connection string; the tool error must not carry the URL or its password
  redacted() { [[ "$1" == "ERROR: ProgrammingError"* && "$1" != *S3CRET* ]]; }
  out=$(LEDGER_DATABASE_URL='postgresql://u:S3CRET%zzPW@127.0.0.1:1/db' sql "SELECT 1")
  row 'a ledger_database_url psycopg cannot parse is an error without the password' "$(yesno redacted "$out")" 'yes'
  bad=$(LEDGER_DATABASE_URL="${LEDGER_DATABASE_URL%/*}/no_such_db" sql "SELECT 1")
  row 'a ledger_database_url that fails is an error, not a fallback to SQLite' "$(yesno grep -q '^ERROR' <<<"$bad")" 'yes'
  echo '  (SQLite path rows skipped on Postgres)'
  exit 0
fi

# A fresh install, started the way .mcp.json starts it (uv run --script): HOME, the working directory and the
# data directory are all new and empty (UV_CACHE_DIR too: setup-uv in CI points it elsewhere). After the first call,
# every new file is inside CLAUDE_PLUGIN_DATA, apart from uv's own cache, which must hold no packages: SQLite needs none.
root=$(mktemp -d "${TMPDIR:-/tmp}/ledger-fresh.XXXXXX")
mkdir -p "$root/home" "$root/cwd" "$root/data/personal-knowledge-shibamasa-plugins"
# PYTHONDONTWRITEBYTECODE: the stock macOS python3 caches its own bytecode under ~/Library/Caches, which is the
# interpreter's doing, not the server's
(cd "$root/cwd" && HOME="$root/home" PYTHONDONTWRITEBYTECODE=1 CLAUDE_PLUGIN_DATA="$root/data/personal-knowledge-shibamasa-plugins" \
  UV_CACHE_DIR="$root/home/.cache/uv" LEDGER_SERVER_CMD="uv run --quiet --script" python3 "$CALL" "SELECT 1") >/dev/null
row 'a fresh install creates relationship-ledger/ledger.sqlite3 in the plugin data directory' "$(yesno [ -f "$root/data/personal-knowledge-shibamasa-plugins/relationship-ledger/ledger.sqlite3" ])" 'yes'
outside=$(cd "$root" && find home cwd -type f ! -path 'home/.cache/uv/*' | wc -l | tr -d ' ')
row 'files written outside the plugin data directory and the uv cache' "$outside" '0'
[ "$outside" = 0 ] || (cd "$root" && find home cwd -type f ! -path 'home/.cache/uv/*' | head -5 | sed 's/^/    outside: /')
row 'psycopg files a fresh SQLite start puts in the uv cache' "$(find "$root/home" -iname '*psycopg*' | wc -l | tr -d ' ')" '0'
rm -rf "$root"

# ledger_sqlite_path moves the file, and then nothing is created in the data directory
moved=$(mktemp -d "${TMPDIR:-/tmp}/ledger-moved.XXXXXX")
LEDGER_SQLITE_PATH="$moved/sub/my-ledger.db" sql "SELECT 1" >/dev/null
row 'ledger_sqlite_path moves the file' "$(yesno [ -f "$moved/sub/my-ledger.db" ])" 'yes'
row 'with ledger_sqlite_path set, nothing is written to the data directory' "$(find "$CLAUDE_PLUGIN_DATA" -type f | wc -l | tr -d ' ')" '0'
rm -rf "$moved"

# The route Claude saved names the store; when that store's setting is missing, nothing opens in its place
out=$(LEDGER_ROUTE=postgres LEDGER_DATABASE_URL= sql "SELECT 1")
row 'ledger_route=postgres without ledger_database_url is an error, not SQLite' "$(yesno grep -q "^ERROR: .*ledger_route is 'postgres' but ledger_database_url is not set" <<<"$out")" 'yes'
row '... and it creates no SQLite file' "$(find "$CLAUDE_PLUGIN_DATA" -type f | wc -l | tr -d ' ')" '0'
out=$(LEDGER_ROUTE=sqlite LEDGER_DATABASE_URL='postgresql://127.0.0.1:1/none' sql "SELECT 1")
row 'ledger_route=sqlite with a ledger_database_url is an error until the two agree' "$(yesno grep -q "^ERROR: .*ledger_route is 'sqlite' but ledger_database_url is set" <<<"$out")" 'yes'
out=$(LEDGER_ROUTE=direct sql "SELECT 1")
row 'a ledger_route that names no store is an error' "$(yesno grep -q "^ERROR: .*ledger_route is 'direct'" <<<"$out")" 'yes'
# ATTACH would create a database file at any path; the server refuses it
attach_to=$(mktemp -d "${TMPDIR:-/tmp}/ledger-attach.XXXXXX")
out=$(sql "ATTACH DATABASE '$attach_to/elsewhere.db' AS other")
row 'ATTACH DATABASE is refused' "$(yesno grep -q '^ERROR' <<<"$out")" 'yes'
row '... and creates no file' "$(find "$attach_to" -type f | wc -l | tr -d ' ')" '0'
rm -rf "$attach_to"
# An option the user never set may reach the server as the literal placeholder
out=$(LEDGER_DATABASE_URL='${user_config.ledger_database_url}' python3 "$CALL" --tool apply_migrations)
row 'an unexpanded ${user_config.ledger_database_url} counts as unset' "$(yesno grep -q '"backend": "sqlite"' <<<"$out")" 'yes'
