#!/bin/bash
# relationship-ledger triggers: updated_at on every table, search_text, and keys that never change.
set -u
. "$(dirname "$0")/ledger_lib.sh"

fresh_db
load_fixtures

# moved TABLE KEYCOL KEY SET: yes when an UPDATE that leaves out updated_at still moves it forward
moved() {
  local before after
  before=$(val "SELECT updated_at FROM $1 WHERE $2 = $3")
  sql "UPDATE $1 SET $4 WHERE $2 = $3" >/dev/null
  after=$(val "SELECT updated_at FROM $1 WHERE $2 = $3")
  [ -n "$before" ] && [ "$after" \> "$before" ]
}
id_of() { val "SELECT id FROM $1 WHERE person_key = '$2' ORDER BY id LIMIT 1"; }

ts=$(val "SELECT updated_at FROM rl_people WHERE person_key = 'taro-example'")
row 'updated_at is UTC text with milliseconds' "$(yesno grep -Eq '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$' <<<"$ts")" 'yes'
other=$(val "SELECT updated_at FROM rl_people WHERE person_key = 'hanako-sample'")
row 'rl_people: an UPDATE moves updated_at' "$(yesno moved rl_people person_key "'taro-example'" "summary = 'updated'")" 'yes'
row 'rl_people: other rows keep their updated_at' "$(yesno [ "$(val "SELECT updated_at FROM rl_people WHERE person_key = 'hanako-sample'")" = "$other" ])" 'yes'
row 'rl_social_accounts: an UPDATE moves updated_at' "$(yesno moved rl_social_accounts id "$(id_of rl_social_accounts example-user)" "notes = 'checked'")" 'yes'
row 'rl_interaction_notes: an UPDATE moves updated_at' "$(yesno moved rl_interaction_notes id "$(id_of rl_interaction_notes taro-example)" "confidence = 5")" 'yes'
row 'rl_prompt_injection_events: an UPDATE moves updated_at' "$(yesno moved rl_prompt_injection_events id "$(id_of rl_prompt_injection_events example-user)" "outcome = 'no_state_change'")" 'yes'
row 'rl_photo_refs: an UPDATE moves updated_at' "$(yesno moved rl_photo_refs id "$(id_of rl_photo_refs taro-example)" "notes = 'kept'")" 'yes'
sql "UPDATE rl_people SET relationship = 'x', updated_at = '2000-01-01T00:00:00.000Z' WHERE person_key = 'hanako-sample'" >/dev/null
row 'an updated_at written by hand is replaced' "$(yesno [ "$(val "SELECT updated_at FROM rl_people WHERE person_key = 'hanako-sample'")" \> 2026 ])" 'yes'

sql "INSERT INTO rl_people (person_key, display_name, search_text, updated_at) VALUES ('jiro-example', 'Jiro', 'forged', '2000-01-01T00:00:00.000Z')" >/dev/null
row 'an INSERT that writes search_text itself gets the computed one' "$(yesno [ "$(val "SELECT search_text FROM rl_people WHERE person_key = 'jiro-example'")" = 'jiro-example jiro  ' ])" 'yes'
row 'an INSERT that writes updated_at itself gets the current time' "$(yesno [ "$(val "SELECT updated_at FROM rl_people WHERE person_key = 'jiro-example'")" \> 2026 ])" 'yes'
sql "INSERT INTO rl_photo_refs (person_key, file_path, consent_basis, updated_at) VALUES ('jiro-example', 'p.jpg', 'provided by the person', '2000-01-01T00:00:00.000Z')" >/dev/null
row 'the same holds on a table without search_text (rl_photo_refs)' "$(yesno [ "$(val "SELECT updated_at FROM rl_photo_refs WHERE file_path = 'p.jpg'")" \> 2026 ])" 'yes'

row 'insert fills rl_people.search_text with NFKC + lower case' "$(yesno [ "$(val "SELECT search_text FROM rl_people WHERE person_key = 'example-user'")" = 'example-user example ユーザー フォロワーで知り合い ' ])" 'yes'
sql "UPDATE rl_people SET summary = 'ＧｉｔＨｕｂ maintainer' WHERE person_key = 'hanako-sample'" >/dev/null
row 'updating summary refreshes search_text' "$(yesno grep -q 'github maintainer' <<<"$(val "SELECT search_text FROM rl_people WHERE person_key = 'hanako-sample'")")" 'yes'
sql "UPDATE rl_social_accounts SET handle = 'Example_User2' WHERE person_key = 'example-user'" >/dev/null
row 'updating a handle refreshes its search_text' "$(yesno grep -q 'example_user2' <<<"$(val "SELECT search_text FROM rl_social_accounts WHERE person_key = 'example-user'")")" 'yes'

err=$(sql "UPDATE rl_people SET person_key = 'taro-2' WHERE person_key = 'taro-example'")
row 'changing person_key is rejected' "$(yesno grep -q 'person_key cannot change' <<<"$err")" 'yes'
row 'the person keeps its key' "$(val "SELECT count(*) FROM rl_people WHERE person_key = 'taro-example'")" '1'
err=$(sql "UPDATE rl_interaction_notes SET id = 999 WHERE person_key = 'taro-example' AND kind = 'task'")
row 'changing a note id is rejected' "$(yesno grep -q 'id cannot change' <<<"$err")" 'yes'
