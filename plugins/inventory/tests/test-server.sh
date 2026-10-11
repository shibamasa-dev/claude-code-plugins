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

  # Cut the server's connection from outside between two calls (a database restart or an idle timeout looks the same)
  cut="!psql '$INVENTORY_PG_ADMIN_URL' -X -q -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${INVENTORY_DATABASE_URL##*/}' AND pid <> pg_backend_pid()\""
  # pid, cut, the call that finds the connection gone, and the call after it
  out=$(python3 "$CALL" --value "SELECT pg_backend_pid()" "$cut" "SELECT pg_backend_pid()" "SELECT pg_backend_pid()")
  row 'the call after the cut is not re-run: it fails saying the connection dropped' "$(yesno grep -q '^ERROR: .*connection dropped while this statement ran' <<<"$(sed -n 2p <<<"$out")")" 'yes'
  new_backend() { local a b; a=$(sed -n 1p <<<"$out"); b=$(sed -n 3p <<<"$out"); [[ "$b" =~ ^[0-9]+$ ]] && [ "$a" != "$b" ]; }
  row 'the call after that succeeds on a new connection' "$(yesno new_backend)" 'yes'
  kept() {  # the error comes back, and the same backend serves the next call
    [ "$(sed -n 2p <<<"$1" | cut -c1-6)" = ERROR: ] && [ "$(sed -n 1p <<<"$1")" = "$(sed -n 3p <<<"$1")" ]
  }
  row 'a syntax error is returned as is and keeps the connection' "$(yesno kept "$(python3 "$CALL" --value "SELECT pg_backend_pid()" "SELEC 1" "SELECT pg_backend_pid()")")" 'yes'

  # A server that accepts the TCP connection and then never answers: the MCP handshake must not wait for it,
  # and the tool call gives up at the connect timeout
  portfile=$(mktemp "${TMPDIR:-/tmp}/inventory-silent.XXXXXX")
  python3 -c '
import socket, sys
s = socket.socket()
s.bind(("127.0.0.1", 0))
s.listen(8)
with open(sys.argv[1], "w") as f:
    f.write(str(s.getsockname()[1]))
held = []
while True:
    held.append(s.accept()[0])  # keep every connection open and silent
' "$portfile" &
  silent=$!; disown "$silent"  # no "Terminated" line when it is killed
  trap 'kill "$silent" 2>/dev/null; rm -f "$portfile"' EXIT
  for _ in $(seq 50); do [ -s "$portfile" ] && break; sleep 0.1; done
  export INVENTORY_DATABASE_URL="postgresql://user@127.0.0.1:$(cat "$portfile")/db"
  quick_list() { local t=$SECONDS; [ "$(python3 "$CALL" --list)" = execute_sql,apply_migrations ] && [ $((SECONDS - t)) -le 5 ]; }
  row 'initialize and tools/list answer at once with a server that never answers' "$(yesno quick_list)" 'yes'
  timed_out() { local t=$SECONDS; grep -qi '^ERROR: .*timeout' <<<"$(sql "SELECT 1")" && [ $((SECONDS - t)) -le 20 ]; }
  row 'the first tool call fails with a timeout error within the connect timeout' "$(yesno timed_out)" 'yes'
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
