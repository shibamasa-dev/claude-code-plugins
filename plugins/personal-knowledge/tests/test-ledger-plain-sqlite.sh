#!/bin/bash
# A client without rl_norm() (python's plain sqlite3, the sqlite3 shell, DB Browser) can still read the SQLite ledger:
# no generated column or view calls the function, only the triggers that fill search_text do.
set -u
. "$(dirname "$0")/ledger_lib.sh"
if is_postgres; then echo '  (SQLite only)'; exit 0; fi

fresh_db
load_fixtures
db="$CLAUDE_PLUGIN_DATA/relationship-ledger/ledger.sqlite3"
plain() { python3 -I -c 'import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
try:
    r = c.execute(sys.argv[2]).fetchone()
    print(r[0] if r else "ok")
except sqlite3.Error as e:
    print("ERROR:", e)' "$db" "$1"; }

for t in rl_people rl_social_accounts rl_interaction_notes rl_prompt_injection_events rl_photo_refs rl_v_people rl_v_search; do
  row "a client without rl_norm() reads $t" "$(yesno [ "$(plain "SELECT count(*) FROM $t")" -gt 0 ])" 'yes'
done
row 'it reads the stored search_text' "$(yesno [ "$(plain "SELECT count(DISTINCT person_key) FROM rl_v_search WHERE search_text LIKE '%example%'")" -gt 0 ])" 'yes'
# Writes that fire a search_text trigger need the function, as the migration header says
row 'its writes to rl_people fail instead of storing a wrong search_text' "$(yesno grep -q '^ERROR' <<<"$(plain "UPDATE rl_people SET summary = 'x' WHERE person_key = 'taro-example'")")" 'yes'
