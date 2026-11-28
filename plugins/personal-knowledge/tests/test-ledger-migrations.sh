#!/bin/bash
# relationship-ledger migrations: applied when the server first opens the database, recorded in rl_schema_migrations,
# and safe to apply twice.
set -u
. "$(dirname "$0")/ledger_lib.sh"

# The schema objects and their definitions, as one string
fingerprint() {
  if is_postgres; then
    val "SELECT md5(string_agg(x, '|' ORDER BY x)) FROM (
           SELECT 'table:' || table_name || ':' || column_name || ':' || data_type || ':' || coalesce(column_default, '')
             FROM information_schema.columns WHERE table_name LIKE 'rl_%'
           UNION ALL SELECT 'view:' || viewname || ':' || definition FROM pg_views WHERE viewname LIKE 'rl_%'
           UNION ALL SELECT 'trigger:' || tgname || ':' || pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname LIKE 'rl_%'
           UNION ALL SELECT 'index:' || indexname || ':' || indexdef FROM pg_indexes WHERE indexname LIKE 'rl_%'
           UNION ALL SELECT 'func:' || p.proname || ':' || md5(p.prosrc) FROM pg_proc p WHERE p.proname LIKE 'rl_%') t(x)"
  else
    val "SELECT group_concat(type || ':' || name || ':' || coalesce(sql, ''), '|') FROM (SELECT * FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name)"
  fi
}
counts="SELECT (SELECT count(*) FROM rl_people) || ':' || (SELECT count(*) FROM rl_social_accounts) || ':'
             || (SELECT count(*) FROM rl_interaction_notes) || ':' || (SELECT count(*) FROM rl_prompt_injection_events)
             || ':' || (SELECT count(*) FROM rl_photo_refs)"

fresh_db
startup=$(python3 "$CALL" --tool apply_migrations)
row 'first start applies 0001_init' "$(yesno grep -q '"applied_on_open": \["0001_init"\]' <<<"$startup")" 'yes'
row 'it is recorded in rl_schema_migrations' "$(yesno [ "$(val "SELECT version FROM rl_schema_migrations")" = 0001_init ])" 'yes'
again=$(python3 "$CALL" --tool apply_migrations)
row 'a second start applies nothing' "$(yesno grep -q '"applied_on_open": \[\], "applied_now": \[\]' <<<"$again")" 'yes'

# Apply the same file again on a database that already has data: forget the version, then restart the server
load_fixtures
before=$(fingerprint)
rows_before=$(val "$counts")
sql "DELETE FROM rl_schema_migrations" >/dev/null
reapplied=$(python3 "$CALL" --tool apply_migrations)
row 're-running 0001_init over an existing schema succeeds' "$(yesno grep -q '"applied_on_open": \["0001_init"\]' <<<"$reapplied")" 'yes'
row 're-running it leaves the schema unchanged' "$(yesno [ "$(fingerprint)" = "$before" ])" 'yes'
row 're-running it leaves the rows unchanged' "$(yesno [ "$(val "$counts")" = "$rows_before" ])" 'yes'
row 'the version is recorded once' "$(val "SELECT count(*) FROM rl_schema_migrations")" '1'
