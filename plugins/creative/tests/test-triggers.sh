#!/bin/bash
# The rules the schema enforces on every write: search_text, updated_at, immutable ids and the CHECK constraints.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
load_fixtures
first="(SELECT id FROM img_attempts WHERE title = 'Mecha raid announcement banner')"

st=$(val "SELECT search_text FROM img_attempts WHERE id = $first")
row 'insert fills search_text with the NFKC-folded request (？ becomes ?) and the tags' "$(yesno grep -qF 'こんな感じの構図の画像作れる? 参照画像のようなゲーム告知バナーをオリジナルで生成。' <<<"$st")" 'yes'
row 'the tags are in search_text' "$(yesno grep -qF '16:9,banner,anime,game-update' <<<"$st")" 'yes'
row 'search_text is lower case' "$(yesno grep -q 'mecha raid announcement banner' <<<"$st")" 'yes'
sql "UPDATE img_attempts SET notes = notes || ' 再利用はﾀｲﾄﾙ配置のみ' WHERE id = $first" >/dev/null
row 'updating notes refreshes search_text, NFKC-folded' "$(yesno grep -q 'タイトル配置のみ' <<<"$(val "SELECT search_text FROM img_attempts WHERE id = $first")")" 'yes'

ts=$(val "SELECT updated_at FROM img_attempts WHERE id = $first")
other=$(val "SELECT updated_at FROM img_attempts WHERE title = 'Original mecha announcement banner v2'")
row 'updated_at is UTC text with milliseconds' "$(yesno grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$' <<<"$ts")" 'yes'
sql "UPDATE img_attempts SET status = 'superseded' WHERE id = $first" >/dev/null
row 'an UPDATE that leaves out updated_at still moves it forward' "$(yesno [ "$(val "SELECT updated_at FROM img_attempts WHERE id = $first")" \> "$ts" ])" 'yes'
row 'other rows keep their updated_at' "$(yesno [ "$(val "SELECT updated_at FROM img_attempts WHERE title = 'Original mecha announcement banner v2'")" = "$other" ])" 'yes'
rts=$(val "SELECT updated_at FROM img_references WHERE label = 'game-update-banner-reference'")
sql "UPDATE img_references SET role = 'none' WHERE label = 'game-update-banner-reference'" >/dev/null
row 'updating a reference moves its updated_at' "$(yesno [ "$(val "SELECT updated_at FROM img_references WHERE label = 'game-update-banner-reference'")" \> "$rts" ])" 'yes'
# The schema owns search_text and updated_at on both stores: a value an UPDATE writes itself does not stick
ts=$(val "SELECT updated_at FROM img_attempts WHERE id = $first")
sql "UPDATE img_attempts SET search_text = 'tampered', updated_at = '2000-01-01T00:00:00.000Z' WHERE id = $first" >/dev/null
row 'an UPDATE that sets search_text itself is overwritten from the text columns' "$(yesno grep -q 'mecha raid announcement banner' <<<"$(val "SELECT search_text FROM img_attempts WHERE id = $first")")" 'yes'
row 'an UPDATE that sets updated_at itself still moves it forward' "$(yesno [ "$(val "SELECT updated_at FROM img_attempts WHERE id = $first")" \> "$ts" ])" 'yes'
rts=$(val "SELECT updated_at FROM img_references WHERE label = 'game-update-banner-reference'")
sql "UPDATE img_references SET updated_at = '2000-01-01T00:00:00.000Z' WHERE label = 'game-update-banner-reference'" >/dev/null
row 'an UPDATE that sets a reference updated_at itself still moves it forward' "$(yesno [ "$(val "SELECT updated_at FROM img_references WHERE label = 'game-update-banner-reference'")" \> "$rts" ])" 'yes'

row 'changing an attempt id is rejected' "$(yesno grep -q '^ERROR: .*id cannot change' <<<"$(sql "UPDATE img_attempts SET id = 999 WHERE id = $first")")" 'yes'
row 'an unknown status is rejected' "$(yesno grep -q '^ERROR' <<<"$(sql "UPDATE img_attempts SET status = 'done' WHERE id = $first")")" 'yes'
row 'an unknown reference role is rejected' "$(yesno grep -q '^ERROR' <<<"$(sql "UPDATE img_references SET role = 'layout' WHERE label = 'game-update-banner-reference'")")" 'yes'
row 'output_paths that is not a JSON array is rejected' "$(yesno grep -q '^ERROR' <<<"$(sql "INSERT INTO img_attempts (title, request, output_paths) VALUES ('x', 'y', '\"out/a.png\"')")")" 'yes'
row 'a reference to a missing attempt is rejected' "$(yesno grep -q '^ERROR' <<<"$(sql "INSERT INTO img_references (attempt_id, source_path, source_sha256, source_bytes) VALUES (424242, 'a.png', '992635f6d496233cb9a8893ed50da9b6abb4bd0c8a32edc26799b72e5c8135e9', 1)")")" 'yes'
row 'the same source twice on one attempt is rejected' "$(yesno grep -q '^ERROR' <<<"$(sql "INSERT INTO img_references (attempt_id, source_path, source_sha256, source_bytes) VALUES ($first, 'again.png', '992635f6d496233cb9a8893ed50da9b6abb4bd0c8a32edc26799b72e5c8135e9', 498132)")")" 'yes'
row 'deleting an attempt that a refinement builds on is rejected' "$(yesno grep -q '^ERROR' <<<"$(sql "DELETE FROM img_attempts WHERE id = $first")")" 'yes'
sql "DELETE FROM img_attempts WHERE title = 'Original mecha announcement banner v2'" >/dev/null
row 'deleting an attempt deletes its references' "$(val "SELECT count(*) FROM img_references WHERE label = 'mecha-announcement-v2-style-reference'")" '0'
