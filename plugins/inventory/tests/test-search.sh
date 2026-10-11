#!/bin/bash
# Search with the form SKILL.md teaches: search_text LIKE '%' || norm('<term>') || '%' ESCAPE '\'
# norm() folds full-width and half-width forms and case, on the stored side (trigger) and the query side alike.
set -u
. "$(dirname "$0")/lib.sh"

# hits TERM: the item_keys found, comma-separated. TERM is embedded the way SKILL.md says (' doubled, % _ \ escaped by the caller)
hits() {
  local t=${1//\'/\'\'}
  sql "SELECT item_key FROM inv_v_items WHERE search_text LIKE '%' || norm('$t') || '%' ESCAPE '\\' ORDER BY item_key" |
    python3 -c 'import json,sys; print(",".join(r[0] for r in json.load(sys.stdin)["rows"]))'
}

fresh_db
load_fixtures

row 'full-width ＨＡＫＫＯ finds the flux stored as half-width' "$(yesno [ "$(hits 'ＨＡＫＫＯ')" = flux-hakko-fs812 ])" 'yes'
row 'lower-case cf25j680rb finds the part number stored in upper case' "$(yesno [ "$(hits 'cf25j680rb')" = resistor-cf25j680rb ])" 'yes'
row 'half-width katakana finds the soldering iron by its alias' "$(yesno [ "$(hits 'ﾊﾝﾀﾞｺﾞﾃ')" = iron-alientek-t80 ])" 'yes'
row 'half-width parentheses match the full-width ones stored in descr' "$(yesno [ "$(hits '(PIN2.54版)')" = module-m5-stamp-s3a-pin254 ])" 'yes'
row 'kanji alias finds the flux' "$(yesno [ "$(hits '白光')" = flux-hakko-fs812 ])" 'yes'
row 'an escaped % matches only a literal percent sign' "$(yesno [ "$(hits '5\%')" = resistor-cf25j680rb ])" 'yes'
row 'a quote in the term is embedded safely and finds nothing' "$(yesno [ "$(hits "o'clock")" = '' ])" 'yes'
row 'an item you do not have finds nothing' "$(yesno [ "$(hits 'オシロスコープ')" = '' ])" 'yes'
