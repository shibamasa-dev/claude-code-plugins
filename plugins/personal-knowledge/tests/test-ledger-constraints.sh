#!/bin/bash
# Rules the relationship-ledger schema enforces on every write, whoever writes the SQL.
set -u
. "$(dirname "$0")/ledger_lib.sh"

fresh_db
load_fixtures
person() { echo "INSERT INTO rl_people (person_key, display_name) VALUES ('$1', '$2')"; }

row 'a status outside the five is rejected' "$(rejected "UPDATE rl_people SET status = 'enemy' WHERE person_key = 'taro-example'")" 'yes'
row 'an upper-case person_key is rejected' "$(rejected "$(person 'Taro-Example2' 'Taro')")" 'yes'
row 'a person_key with a leading @ is rejected' "$(rejected "$(person '@taro2' 'Taro')")" 'yes'
row 'a person_key with a space is rejected' "$(rejected "$(person 'taro two' 'Taro')")" 'yes'
row 'an empty display_name is rejected' "$(rejected "$(person 'taro2' '')")" 'yes'
row 'a lower-case slug with Japanese text in display_name is accepted' "$(rejected "$(person 'jiro-example' '例 次郎')")" 'no'

social() { echo "INSERT INTO rl_social_accounts (person_key, platform, handle) VALUES ('$1', '$2', '$3')"; }
row 'a handle with a leading @ is rejected' "$(rejected "$(social hanako-sample x '@hanako')")" 'yes'
row 'an upper-case platform is rejected' "$(rejected "$(social hanako-sample X hanako)")" 'yes'
row 'the same handle in another case on the same platform is rejected' "$(rejected "$(social hanako-sample x EXAMPLE_USER)")" 'yes'
row 'the same handle on another platform is accepted' "$(rejected "$(social hanako-sample github example_user)")" 'no'

note() { echo "INSERT INTO rl_interaction_notes (person_key, kind, note, confidence) VALUES ('$1', '$2', '$3', $4)"; }
row 'a note kind outside the six is rejected' "$(rejected "$(note taro-example rumor 'n' NULL)")" 'yes'
row 'confidence 6 is rejected' "$(rejected "$(note taro-example context 'n' 6)")" 'yes'
row 'confidence -1 is rejected' "$(rejected "$(note taro-example context 'n' -1)")" 'yes'
row 'an empty note is rejected' "$(rejected "$(note taro-example context '' 3)")" 'yes'
row 'confidence 0 is accepted' "$(rejected "$(note taro-example context 'n' 0)")" 'no'

row 'a severity outside the four is rejected' "$(rejected "INSERT INTO rl_prompt_injection_events (person_key, summary, severity) VALUES ('example-user', 's', 'apocalyptic')")" 'yes'
row 'a prompt-injection event without a summary is rejected' "$(rejected "INSERT INTO rl_prompt_injection_events (person_key, summary) VALUES ('example-user', '')")" 'yes'

row 'a photo ref with neither file_path nor source_url is rejected' "$(rejected "INSERT INTO rl_photo_refs (person_key, consent_basis) VALUES ('taro-example', 'provided by the person')")" 'yes'
row 'a photo ref without consent_basis is rejected' "$(rejected "INSERT INTO rl_photo_refs (person_key, file_path) VALUES ('taro-example', 'photos/a.jpg')")" 'yes'
row 'a photo ref with an empty consent_basis is rejected' "$(rejected "INSERT INTO rl_photo_refs (person_key, file_path, consent_basis) VALUES ('taro-example', 'photos/a.jpg', '')")" 'yes'

row 'a note for a person who is not in the ledger is rejected' "$(rejected "$(note ghost context 'n' NULL)")" 'yes'
row 'an account for a person who is not in the ledger is rejected' "$(rejected "$(social ghost x ghost_handle)")" 'yes'
sql "DELETE FROM rl_people WHERE person_key = 'taro-example'" >/dev/null
row "deleting a person deletes their accounts, notes and photo refs" "$(val "SELECT (SELECT count(*) FROM rl_social_accounts WHERE person_key = 'taro-example') + (SELECT count(*) FROM rl_interaction_notes WHERE person_key = 'taro-example') + (SELECT count(*) FROM rl_photo_refs WHERE person_key = 'taro-example')")" '0'
