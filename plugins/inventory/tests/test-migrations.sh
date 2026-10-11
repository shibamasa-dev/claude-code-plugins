#!/bin/bash
# Migrations: applied at server start, recorded in inv_schema_migrations, and safe to apply twice.
set -u
. "$(dirname "$0")/lib.sh"

# The schema objects and their definitions, as one string
fingerprint() {
  if is_postgres; then
    val "SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (
           SELECT 'table:' || table_name || ':' || column_name || ':' || data_type || ':' || coalesce(column_default, '')
             FROM information_schema.columns WHERE table_name LIKE 'inv_%'
           UNION ALL SELECT 'view:' || viewname || ':' || definition FROM pg_views WHERE viewname LIKE 'inv_%'
           UNION ALL SELECT 'trigger:' || tgname || ':' || pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname LIKE 'inv_%'
           UNION ALL SELECT 'index:' || indexname || ':' || indexdef FROM pg_indexes WHERE indexname LIKE 'inv_%'
           UNION ALL SELECT 'func:' || p.proname || ':' || md5(p.prosrc) FROM pg_proc p WHERE p.proname = 'norm' OR p.proname LIKE 'inv_%') t(x)"
  else
    val "SELECT group_concat(type || ':' || name || ':' || coalesce(sql, ''), '|') FROM (SELECT * FROM sqlite_master ORDER BY name)"
  fi
}

fresh_db
startup=$(python3 "$CALL" --tool apply_migrations)
row 'first start applies 0001_init' "$(yesno grep -q '"applied_at_startup": \["0001_init"\]' <<<"$startup")" 'yes'
row 'it is recorded in inv_schema_migrations' "$(yesno [ "$(val "SELECT version FROM inv_schema_migrations")" = 0001_init ])" 'yes'
row 'the 27 seed categories are there' "$(yesno [ "$(val "SELECT count(*) FROM inv_categories")" = 27 ])" 'yes'
again=$(python3 "$CALL" --tool apply_migrations)
row 'a second start applies nothing' "$(yesno grep -q '"applied_at_startup": \[\], "applied_now": \[\]' <<<"$again")" 'yes'

# Apply the same file again on a database that already has data: forget the version, then restart the server
load_fixtures
before=$(fingerprint)
items_before=$(val "SELECT count(*) || ':' || sum(coalesce(qty, 0)) FROM inv_items")
sql "DELETE FROM inv_schema_migrations" >/dev/null
reapplied=$(python3 "$CALL" --tool apply_migrations)
row 're-running 0001_init over an existing schema succeeds' "$(yesno grep -q '"applied_at_startup": \["0001_init"\]' <<<"$reapplied")" 'yes'
row 're-running it leaves the schema unchanged' "$(yesno [ "$(fingerprint)" = "$before" ])" 'yes'
row 're-running it leaves the rows unchanged' "$(yesno [ "$(val "SELECT count(*) || ':' || sum(coalesce(qty, 0)) FROM inv_items")" = "$items_before" ])" 'yes'
row 're-running it does not duplicate the seed categories' "$(yesno [ "$(val "SELECT count(*) FROM inv_categories")" = 27 ])" 'yes'
