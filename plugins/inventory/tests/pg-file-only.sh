#!/bin/bash
# The connector route: Claude sends migrations/postgres/*.sql through the connector's migration tool, with no
# MCP server involved. Stand-in: run the file with psql on a fresh database, twice, then check the schema works.
# Run by run-postgres.sh only (needs INVENTORY_PG_ADMIN_URL and psql).
set -u
. "$(dirname "$0")/lib.sh"
FILE="$TESTS/../migrations/postgres/0001_init.sql"

fresh_db
p() { PGOPTIONS='-c client_min_messages=warning' psql "$INVENTORY_DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 "$@"; }
# Supabase-like API roles that get every new table and view by default
p -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon; END IF; END \$\$"
p -c "ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO anon"
row 'the file runs on its own' "$(yesno p -f "$FILE")" 'yes'
row 'the file runs a second time' "$(yesno p -f "$FILE")" 'yes'
row 'the version is recorded once' "$(yesno [ "$(p -c "SELECT count(*) FROM inv_schema_migrations")" = 1 ])" 'yes'
p -c "INSERT INTO inv_items (item_key, category, descr, aliases) VALUES ('iron-alientek-t80', 'tool_solder', 'ALIENTEK T80 スマートはんだごて', 'ハンダゴテ')"
row 'norm() search works without the MCP server' "$(yesno [ "$(p -c "SELECT item_key FROM inv_v_items WHERE search_text LIKE '%' || norm('ﾊﾝﾀﾞｺﾞﾃ') || '%' ESCAPE '\\'")" = iron-alientek-t80 ])" 'yes'
row 'RLS is on for inv_items' "$(yesno [ "$(p -c "SELECT relrowsecurity FROM pg_class WHERE relname = 'inv_items'")" = t ])" 'yes'
row 'the API role anon cannot read the views' "$(yesno [ "$(p -c "SELECT has_table_privilege('anon', 'inv_v_items', 'SELECT')")" = f ])" 'yes'
row 'a later server start sees the schema as applied' "$(yesno grep -q '"applied_at_startup": \[\]' <<<"$(python3 "$CALL" --tool apply_migrations)")" 'yes'
