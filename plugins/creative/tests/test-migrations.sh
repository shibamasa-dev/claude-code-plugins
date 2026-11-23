#!/bin/bash
# Migrations: applied when the server first opens the database, recorded in img_schema_migrations, and safe to apply twice.
set -u
. "$(dirname "$0")/lib.sh"

# The schema objects and their definitions, as one string
fingerprint() {
  if is_postgres; then
    val "SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (
           SELECT 'table:' || table_name || ':' || column_name || ':' || data_type || ':' || coalesce(column_default, '')
             FROM information_schema.columns WHERE table_name LIKE 'img_%'
           UNION ALL SELECT 'view:' || viewname || ':' || definition FROM pg_views WHERE viewname LIKE 'img_%'
           UNION ALL SELECT 'trigger:' || tgname || ':' || pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname LIKE 'img_%'
           UNION ALL SELECT 'index:' || indexname || ':' || indexdef FROM pg_indexes WHERE indexname LIKE 'img_%'
           UNION ALL SELECT 'func:' || p.proname || ':' || md5(p.prosrc) FROM pg_proc p WHERE p.proname LIKE 'img_%') t(x)"
  else
    val "SELECT group_concat(type || ':' || name || ':' || coalesce(sql, ''), '|') FROM (SELECT * FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name)"
  fi
}

fresh_db
startup=$(python3 "$CALL" --tool apply_migrations)
row 'first start applies 0001_init' "$(yesno grep -q '"applied_on_open": \["0001_init"\]' <<<"$startup")" 'yes'
row 'it is recorded in img_schema_migrations' "$(yesno [ "$(val "SELECT version FROM img_schema_migrations")" = 0001_init ])" 'yes'
again=$(python3 "$CALL" --tool apply_migrations)
row 'a second start applies nothing' "$(yesno grep -q '"applied_on_open": \[\], "applied_now": \[\]' <<<"$again")" 'yes'

# Apply the same file again on a database that already has data: forget the version, then restart the server
load_fixtures
before=$(fingerprint)
rows_before=$(val "SELECT (SELECT count(*) FROM img_attempts) || ':' || (SELECT count(*) FROM img_references)")
sql "DELETE FROM img_schema_migrations" >/dev/null
reapplied=$(python3 "$CALL" --tool apply_migrations)
row 're-running 0001_init over an existing schema succeeds' "$(yesno grep -q '"applied_on_open": \["0001_init"\]' <<<"$reapplied")" 'yes'
row 're-running it leaves the schema unchanged' "$(yesno [ "$(fingerprint)" = "$before" ])" 'yes'
row 're-running it leaves the rows unchanged' "$(yesno [ "$(val "SELECT (SELECT count(*) FROM img_attempts) || ':' || (SELECT count(*) FROM img_references)")" = "$rows_before" ])" 'yes'
