#!/bin/bash
# Registration is INSERT ... ON CONFLICT (item_key) DO UPDATE SET <only the columns written>.
# A second photo of the same bag must not add a row, and columns left out must keep their values.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
load_fixtures

before=$(sql "SELECT descr, mpn, manufacturer, aliases, attrs FROM inv_items WHERE item_key = 'jumper-breadboard-mm'")
# A recount of the jumper wires: only qty and needs_review are written
sql "INSERT INTO inv_items (item_key, category, descr, qty, needs_review)
     VALUES ('jumper-breadboard-mm', 'jumper', 'ジャンパーワイヤ', 62, NULL)
     ON CONFLICT (item_key) DO UPDATE SET qty = excluded.qty, needs_review = excluded.needs_review" >/dev/null

row 'the upsert does not add a row' "$(yesno [ "$(val "SELECT count(*) FROM inv_items WHERE item_key = 'jumper-breadboard-mm'")" = 1 ])" 'yes'
row 'the written column changes' "$(yesno [ "$(val "SELECT qty FROM inv_items WHERE item_key = 'jumper-breadboard-mm'")" = 62 ])" 'yes'
row 'a column written as NULL in SET becomes NULL' "$(yesno [ "$(val "SELECT needs_review FROM inv_items WHERE item_key = 'jumper-breadboard-mm'")" = NULL ])" 'yes'
row 'columns not in SET keep their values, even descr given in VALUES' "$(yesno [ "$(sql "SELECT descr, mpn, manufacturer, aliases, attrs FROM inv_items WHERE item_key = 'jumper-breadboard-mm'")" = "$before" ])" 'yes'
