#!/bin/bash
# qty: NULL means not counted, 0 means none left. The schema keeps them apart and rejects negatives.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
load_fixtures

row 'qty left out of the INSERT stays NULL (no default)' "$(yesno [ "$(val "SELECT qty FROM inv_items WHERE item_key = 'switch-push-white-rect'")" = NULL ])" 'yes'
sql "UPDATE inv_items SET qty = 0 WHERE item_key = 'resistor-cf25j680rb'" >/dev/null
row 'qty = 0 finds only the used-up item' "$(yesno [ "$(val "SELECT item_key FROM inv_items WHERE qty = 0")" = resistor-cf25j680rb ])" 'yes'
row 'qty IS NULL finds only the uncounted item' "$(yesno [ "$(val "SELECT item_key FROM inv_items WHERE qty IS NULL")" = switch-push-white-rect ])" 'yes'
row 'a negative qty is rejected' "$(yesno grep -q '^ERROR' <<<"$(sql "UPDATE inv_items SET qty = -1 WHERE item_key = 'iron-alientek-t80'")")" 'yes'
