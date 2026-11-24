#!/bin/bash
# The MCP server itself: its tools, where it puts the data, and that it never switches stores on its own.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
row 'tools/list offers exactly execute_sql and apply_migrations' "$(yesno [ "$(python3 "$CALL" --list)" = execute_sql,apply_migrations ])" 'yes'
out=$(CREATIVE_HISTORY_ROUTE=connector sql "SELECT 1")
row 'with route=connector every call is refused and points at the connector' "$(yesno grep -q "^ERROR: .*route is 'connector'" <<<"$out")" 'yes'

# psycopg's errors quote the connection string; the tool error must not carry the URL or its password.
# The real launch command, so psycopg (added through uv) produces the error
redacted() { [[ "$1" == "ERROR: ProgrammingError"* && "$1" != *S3CRET* ]]; }
out=$(CREATIVE_HISTORY_SERVER_CMD="uv run --quiet --script" CREATIVE_HISTORY_DATABASE_URL='postgresql://u:S3CRET%zzPW@127.0.0.1:1/db' sql "SELECT 1")
row 'a database_url psycopg cannot parse is an error without the password' "$(yesno redacted "$out")" 'yes'
out=$(CREATIVE_HISTORY_SERVER_CMD="uv run --quiet --script" CREATIVE_HISTORY_DATABASE_URL='u:S3CRETPW@127.0.0.1:1/db' sql "SELECT 1")
row 'a database_url without a scheme is an error without the password' "$(yesno redacted "$out")" 'yes'

if is_postgres; then
  bad=$(CREATIVE_HISTORY_DATABASE_URL="${CREATIVE_HISTORY_DATABASE_URL%/*}/no_such_db" sql "SELECT 1")
  row 'a database_url that fails is an error, not a fallback to SQLite' "$(yesno grep -q '^ERROR' <<<"$bad")" 'yes'
  echo '  (SQLite path rows skipped on Postgres)'
  exit 0
fi

# A fresh install, started the way .mcp.json starts it (uv run --script): HOME, the working directory and the
# data directory are all new and empty (UV_CACHE_DIR too: setup-uv in CI points it elsewhere). After the first call, every new file is inside CLAUDE_PLUGIN_DATA, apart
# from uv's own cache, which must hold no packages: the SQLite route needs none.
root=$(mktemp -d "${TMPDIR:-/tmp}/creative-fresh.XXXXXX")
mkdir -p "$root/home" "$root/cwd" "$root/data/creative-shibamasa-plugins"
# PYTHONDONTWRITEBYTECODE: the stock macOS python3 caches its own bytecode under ~/Library/Caches, which is the
# interpreter's doing, not the server's
(cd "$root/cwd" && HOME="$root/home" PYTHONDONTWRITEBYTECODE=1 CLAUDE_PLUGIN_DATA="$root/data/creative-shibamasa-plugins" \
  UV_CACHE_DIR="$root/home/.cache/uv" CREATIVE_HISTORY_SERVER_CMD="uv run --quiet --script" python3 "$CALL" "SELECT 1") >/dev/null
row 'a fresh install creates image-history/history.sqlite3 in the plugin data directory' "$(yesno [ -f "$root/data/creative-shibamasa-plugins/image-history/history.sqlite3" ])" 'yes'
outside=$(cd "$root" && find home cwd -type f ! -path 'home/.cache/uv/*' | wc -l | tr -d ' ')
row 'files written outside the plugin data directory and the uv cache' "$outside" '0'
[ "$outside" = 0 ] || (cd "$root" && find home cwd -type f ! -path 'home/.cache/uv/*' | head -5 | sed 's/^/    outside: /')
row 'psycopg files a fresh SQLite start puts in the uv cache' "$(find "$root/home" -iname '*psycopg*' | wc -l | tr -d ' ')" '0'

# The route Claude saved names the store; when that store's setting is missing, nothing opens in its place
out=$(CREATIVE_HISTORY_ROUTE=postgres CREATIVE_HISTORY_DATABASE_URL= sql "SELECT 1")
row 'route=postgres without database_url is an error, not SQLite' "$(yesno grep -q "^ERROR: .*route is 'postgres' but database_url is not set" <<<"$out")" 'yes'
out=$(CREATIVE_HISTORY_ROUTE=sqlite CREATIVE_HISTORY_DATABASE_URL='postgresql://127.0.0.1:1/none' sql "SELECT 1")
row 'route=sqlite with a database_url is an error until the two agree' "$(yesno grep -q "^ERROR: .*route is 'sqlite' but database_url is set" <<<"$out")" 'yes'
out=$(CREATIVE_HISTORY_ROUTE=direct sql "SELECT 1")
row 'a route that names no store is an error' "$(yesno grep -q "^ERROR: .*route is 'direct'" <<<"$out")" 'yes'

sql "SELECT 1" >/dev/null
CREATIVE_HISTORY_SQLITE_PATH="$CLAUDE_PLUGIN_DATA/elsewhere/my.db" sql "SELECT 1" >/dev/null
row 'sqlite_path moves the file' "$(yesno [ -f "$CLAUDE_PLUGIN_DATA/elsewhere/my.db" ])" 'yes'
# An option the user never set may reach the server as the literal placeholder
out=$(CREATIVE_HISTORY_DATABASE_URL='${user_config.database_url}' python3 "$CALL" --tool apply_migrations)
row 'an unexpanded ${user_config.database_url} counts as unset' "$(yesno grep -q '"backend": "sqlite"' <<<"$out")" 'yes'
out=$(CREATIVE_HISTORY_DATABASE_URL='postgresql://127.0.0.1:1/none' sql "SELECT 1")
row 'a database_url that fails is an error, not a fallback to SQLite' "$(yesno grep -q '^ERROR' <<<"$out")" 'yes'
rm -rf "$root"
