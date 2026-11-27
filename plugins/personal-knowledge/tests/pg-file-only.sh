#!/bin/bash
# The connector route: Claude sends migrations/postgres/*.sql through the connector's migration tool, with no
# MCP server involved. Stand-in: run the file with psql on a fresh database, twice, then check the schema works.
# Run by run-postgres.sh only (needs LEDGER_PG_ADMIN_URL and psql).
set -u
. "$(dirname "$0")/ledger_lib.sh"
FILE="$TESTS/../migrations/postgres/0001_init.sql"

fresh_db
p() { PGOPTIONS='-c client_min_messages=warning' psql "$LEDGER_DATABASE_URL" -X -q -A -t -v ON_ERROR_STOP=1 "$@"; }
# Supabase-like API roles that get every new table and view by default
p -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon; END IF; END \$\$"
p -c "ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO anon"
row 'the file runs on its own' "$(yesno p -f "$FILE")" 'yes'
row 'the file runs a second time' "$(yesno p -f "$FILE")" 'yes'
row 'the version is recorded once' "$(yesno [ "$(p -c "SELECT count(*) FROM rl_schema_migrations")" = 1 ])" 'yes'
p -c "INSERT INTO rl_people (person_key, display_name, relationship) VALUES ('taro-example', 'Taro Example', 'Example Meetup で名刺交換')"
row 'rl_norm() search works without the MCP server' "$(yesno [ "$(p -c "SELECT DISTINCT person_key FROM rl_v_search WHERE search_text LIKE '%' || rl_norm('ＭＥＥＴＵＰ') || '%' ESCAPE '\\'")" = taro-example ])" 'yes'
row 'RLS is on for rl_people' "$(yesno [ "$(p -c "SELECT relrowsecurity FROM pg_class WHERE relname = 'rl_people'")" = t ])" 'yes'
row 'the API role anon cannot read rl_v_people' "$(yesno [ "$(p -c "SELECT has_table_privilege('anon', 'rl_v_people', 'SELECT')")" = f ])" 'yes'
row 'the API role anon cannot read rl_v_search' "$(yesno [ "$(p -c "SELECT has_table_privilege('anon', 'rl_v_search', 'SELECT')")" = f ])" 'yes'
row 'a later server start sees the schema as applied' "$(yesno grep -q '"applied_on_open": \[\]' <<<"$(python3 "$CALL" --tool apply_migrations)")" 'yes'
