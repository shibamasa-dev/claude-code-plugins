#!/bin/bash
# Rules the schema enforces on every write, whoever writes the SQL.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
load_fixtures

rejected() { yesno grep -q '^ERROR' <<<"$(sql "$1")"; }
row 'needs_review with spaces is rejected (column names, comma-separated)' "$(rejected "UPDATE inv_items SET needs_review = 'qty, manufacturer' WHERE item_key = 'iron-alientek-t80'")" 'yes'
row 'an empty needs_review is rejected (NULL means confirmed)' "$(rejected "UPDATE inv_items SET needs_review = '' WHERE item_key = 'iron-alientek-t80'")" 'yes'
row 'needs_review can point into attrs' "$(rejected "UPDATE inv_items SET needs_review = 'qty,attrs.length' WHERE item_key = 'iron-alientek-t80'")" 'no'
row 'attrs must be a JSON object' "$(rejected "UPDATE inv_items SET attrs = '[1, 2]' WHERE item_key = 'iron-alientek-t80'")" 'yes'
row 'an unknown category is rejected' "$(rejected "INSERT INTO inv_items (item_key, category, descr) VALUES ('scope-x', 'oscilloscope', 'Oscilloscope')")" 'yes'
sql "INSERT INTO inv_categories (code, name, kind, sort) VALUES ('tool_scope', 'Oscilloscopes', 'tool', 325)" >/dev/null
row 'a category the user added is accepted' "$(rejected "INSERT INTO inv_items (item_key, category, descr) VALUES ('scope-x', 'tool_scope', 'Oscilloscope')")" 'no'
row 'a category kind outside the four is rejected' "$(rejected "INSERT INTO inv_categories (code, name, kind) VALUES ('food', 'Food', 'grocery')")" 'yes'
row 'a second item with the same maker and part number is rejected' "$(rejected "INSERT INTO inv_items (item_key, category, descr, mpn, manufacturer) VALUES ('t80-again', 'tool_solder', 'T80', 'T80', 'ALIENTEK')")" 'yes'
row 'attrs ->> reads a key on both databases' "$(yesno [ "$(val "SELECT attrs ->> 'pack_qty' FROM inv_items WHERE item_key = 'resistor-cf25j680rb'")" = 100 ])" 'yes'
