#!/bin/bash
# The three triggers on inv_items: search_text, updated_at, and the immutable item_key.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
load_fixtures

st=$(val "SELECT search_text FROM inv_items WHERE item_key = 'flux-hakko-fs812'")
row 'insert fills search_text with the normalized text' "$(yesno [ "$st" = 'hakko flux fs-812 ハロゲンフリーフラックス 10ml fs-812 白光(hakko) フラックス,flux,hakko,白光,ハロゲンフリー,はんだ付け補助,fs-812' ])" 'yes'
sql "UPDATE inv_items SET aliases = aliases || ',ﾌﾗｯｸｽ液' WHERE item_key = 'flux-hakko-fs812'" >/dev/null
row 'updating aliases refreshes search_text' "$(yesno grep -q 'フラックス液' <<<"$(val "SELECT search_text FROM inv_items WHERE item_key = 'flux-hakko-fs812'")")" 'yes'
sql "UPDATE inv_items SET note = 'checked' WHERE item_key = 'flux-hakko-fs812'" >/dev/null
row 'updating another column leaves search_text alone' "$(yesno grep -q 'フラックス液' <<<"$(val "SELECT search_text FROM inv_items WHERE item_key = 'flux-hakko-fs812'")")" 'yes'

ts=$(val "SELECT updated_at FROM inv_items WHERE item_key = 'resistor-cf25j680rb'")
other=$(val "SELECT updated_at FROM inv_items WHERE item_key = 'iron-alientek-t80'")
row 'updated_at is UTC text with milliseconds' "$(yesno grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$' <<<"$ts")" 'yes'
sql "UPDATE inv_items SET qty = 99 WHERE item_key = 'resistor-cf25j680rb'" >/dev/null
ts2=$(val "SELECT updated_at FROM inv_items WHERE item_key = 'resistor-cf25j680rb'")
row 'an UPDATE that leaves out updated_at still moves it forward' "$(yesno [ "$ts2" \> "$ts" ])" 'yes'
row 'other rows keep their updated_at' "$(yesno [ "$(val "SELECT updated_at FROM inv_items WHERE item_key = 'iron-alientek-t80'")" = "$other" ])" 'yes'

err=$(sql "UPDATE inv_items SET item_key = 'resistor-680' WHERE item_key = 'resistor-cf25j680rb'")
row 'changing item_key is rejected' "$(yesno grep -q 'item_key cannot change' <<<"$err")" 'yes'
row 'the row keeps its item_key' "$(yesno [ "$(val "SELECT count(*) FROM inv_items WHERE item_key = 'resistor-cf25j680rb'")" = 1 ])" 'yes'
