#!/bin/bash
# The SQL forms relationship-ledger's SKILL.md teaches, each run as written there.
# The behaviours come from the source CLI's tests: status kept when left out, a handle moves to the latest person,
# a URL kept when a later call has none, lookups that accept @ and any case, search over notes and handles.
set -u
. "$(dirname "$0")/ledger_lib.sh"

fresh_db
load_fixtures

# Person upsert (SKILL.md section 5): SET names only the columns given, so status (and summary) keep their values when left out
upsert_person() {  # KEY NAME RELATIONSHIP [STATUS]
  if [ -n "${4:-}" ]; then
    sql "INSERT INTO rl_people (person_key, display_name, relationship, status) VALUES ('$1', '$2', '$3', '$4')
         ON CONFLICT (person_key) DO UPDATE SET display_name = excluded.display_name,
           relationship = excluded.relationship, status = excluded.status" >/dev/null
  else
    sql "INSERT INTO rl_people (person_key, display_name, relationship) VALUES ('$1', '$2', '$3')
         ON CONFLICT (person_key) DO UPDATE SET display_name = excluded.display_name,
           relationship = excluded.relationship" >/dev/null
  fi
}
status_of() { val "SELECT status FROM rl_people WHERE person_key = '$1'"; }

upsert_person jiro-example 'Jiro Example' 'met online'
row 'a new person without a status is active' "$(status_of jiro-example)" 'active'
upsert_person example-user 'Example User' 'follower, met at a meetup'
row 'an upsert without status keeps the existing status' "$(status_of example-user)" 'watch'
row 'an upsert keeps columns it does not name' "$(yesno [ "$(val "SELECT summary FROM rl_people WHERE person_key = 'taro-example'")" = "$(upsert_person taro-example 'Taro Example' 'card'; val "SELECT summary FROM rl_people WHERE person_key = 'taro-example'")" ])" 'yes'
upsert_person example-user 'Example User' 'follower' blocked
row 'an upsert with a status sets it' "$(status_of example-user)" 'blocked'
row 'the upsert adds no row' "$(val "SELECT count(*) FROM rl_people WHERE person_key = 'example-user'")" '1'

# Account upsert (SKILL.md section 5): one account belongs to one person; a later call without a URL keeps the known one
upsert_social() {  # PERSON PLATFORM HANDLE URL-or-NULL
  local url=NULL; [ "$4" != NULL ] && url="'$4'"
  sql "INSERT INTO rl_social_accounts (person_key, platform, handle, url) VALUES ('$1', '$2', '$3', $url)
       ON CONFLICT (platform, lower(handle)) DO UPDATE SET person_key = excluded.person_key, handle = excluded.handle,
         url = coalesce(excluded.url, rl_social_accounts.url), notes = coalesce(excluded.notes, rl_social_accounts.notes)" >/dev/null
}
upsert_social hanako-sample github example-hanako 'https://github.com/example-hanako'
upsert_social hanako-sample github example-hanako NULL
row 'a later upsert without a URL keeps the URL' "$(yesno [ "$(val "SELECT url FROM rl_social_accounts WHERE handle = 'example-hanako'")" = https://github.com/example-hanako ])" 'yes'
upsert_social jiro-example x Example_User NULL
row 'the same handle in another case moves to the latest person' "$(val "SELECT person_key FROM rl_social_accounts WHERE platform = 'x' AND lower(handle) = 'example_user'")" 'jiro-example'
row '... without adding a row' "$(val "SELECT count(*) FROM rl_social_accounts WHERE platform = 'x' AND lower(handle) = 'example_user'")" '1'
row '... and keeps the URL it had' "$(yesno [ "$(val "SELECT url FROM rl_social_accounts WHERE platform = 'x' AND lower(handle) = 'example_user'")" = https://x.com/example_user ])" 'yes'
row 'rl_v_people shows the account as x_handle' "$(val "SELECT x_handle FROM rl_v_people WHERE person_key = 'jiro-example'")" 'Example_User'

# Lookup by key or handle (SKILL.md section 4): Claude drops a leading @ and the term goes through lower() on both sides
lookup() { val "SELECT person_key FROM rl_people WHERE person_key = lower('$1')
                 OR person_key IN (SELECT person_key FROM rl_social_accounts WHERE lower(handle) = lower('$1'))"; }
row 'a lookup by key in upper case finds the person' "$(lookup 'TARO-EXAMPLE')" 'taro-example'
row 'a lookup by handle in another case finds its person' "$(lookup 'EXAMPLE_user')" 'jiro-example'

# Search (SKILL.md section 4): every searchable text, NFKC-normalized and lower-cased on both sides
search() { sql "SELECT * FROM rl_v_people
                WHERE person_key IN (SELECT person_key FROM rl_v_search
                                      WHERE search_text LIKE '%' || rl_norm('$1') || '%' ESCAPE '\\')
                ORDER BY updated_at DESC" |
           python3 -c 'import json,sys; print(",".join(r[0] for r in json.load(sys.stdin)["rows"]) or "none")'; }
row 'a full-width upper-case term finds a note' "$(search 'ＧＯＶＥＲＮＡＮＣＥ')" 'taro-example'
row 'an upper-case term finds a handle' "$(search 'EXAMPLE-HANAKO')" 'hanako-sample'
row 'a full-width term finds the summary stored half-width' "$(search 'Ｅｘａｍｐｌｅ株式会社')" 'taro-example'
row 'a term nobody matches finds nothing' "$(search 'no-such-person')" 'none'

# The watch list (SKILL.md section 8)
row 'the watch list holds watch, avoid and blocked people only' "$(sql "SELECT person_key, display_name, status, relationship, prompt_injection_count FROM rl_v_people WHERE status IN ('watch', 'avoid', 'blocked') ORDER BY status, person_key;" | python3 -c 'import json,sys; print(",".join(r[0] for r in json.load(sys.stdin)["rows"]))')" 'example-user'

# A photo reference (SKILL.md section 5) with a consent basis
sql "INSERT INTO rl_photo_refs (person_key, file_path, source_url, consent_basis, notes) VALUES ('jiro-example', 'photos/jiro-example.jpg', NULL, 'provided by the person for this ledger', NULL)" >/dev/null
row 'a photo reference with a consent basis is recorded and counted' "$(val "SELECT photo_ref_count FROM rl_v_people WHERE person_key = 'jiro-example'")" '1'

# Prompt-injection events are counted, never folded into the person
sql "INSERT INTO rl_prompt_injection_events (person_key, source_kind, summary) VALUES ('jiro-example', 'x', 'second-try')" >/dev/null
sql "INSERT INTO rl_prompt_injection_events (person_key, source_kind, summary, severity) VALUES ('jiro-example', 'x', 'third-try', 'playful')" >/dev/null
row 'rl_v_people counts the events' "$(val "SELECT prompt_injection_count FROM rl_v_people WHERE person_key = 'jiro-example'")" '2'
row '... and the status stays as it was' "$(status_of jiro-example)" 'active'
id=$(val "SELECT id FROM rl_prompt_injection_events WHERE summary = 'second-try'")
sql "UPDATE rl_prompt_injection_events SET outcome = 'no_state_change' WHERE id = $id" >/dev/null
row 'an event update changes only the columns it names' "$(val "SELECT summary || '|' || severity || '|' || outcome FROM rl_prompt_injection_events WHERE id = $id")" 'second-try|low|no_state_change'
row 'an update of an event that does not exist reports rowcount 0' "$(val "UPDATE rl_prompt_injection_events SET outcome = 'x' WHERE id = 999999")" '0'

# Business-card intake (SKILL.md section 7): the person, then one meeting, one context and one task note, in one
# execute_transaction call
python3 "$CALL" --tx "INSERT INTO rl_people (person_key, display_name, relationship, summary, source)
     VALUES ('saburo-sample', 'Saburo Sample', 'Example Meetup #3 で名刺交換 / Sample Inc.', 'Engineer / Sample Inc.', 'user-provided business card')
     ON CONFLICT (person_key) DO UPDATE SET display_name = excluded.display_name, relationship = excluded.relationship,
       summary = excluded.summary, source = excluded.source" \
    "INSERT INTO rl_interaction_notes (person_key, kind, note, confidence, occurred_at)
     VALUES ('saburo-sample', 'meeting', 'event: Example Meetup #3; place: Example Hall; met_at: 2026-06-10; conversation: test automation', 4, '2026-06-10')" \
    "INSERT INTO rl_interaction_notes (person_key, kind, note, confidence)
     VALUES ('saburo-sample', 'context', 'Business card fields: company: Sample Inc.; title: Engineer; email: saburo@example.com', 4)" \
    "INSERT INTO rl_interaction_notes (person_key, kind, note) VALUES ('saburo-sample', 'task', 'Follow-up: send the slides')" >/dev/null
# The same intake for another card with one bad statement (a note kind outside the six) commits nothing
out=$(python3 "$CALL" --tx "INSERT INTO rl_people (person_key, display_name, source) VALUES ('shiro-sample', 'Shiro Sample', 'user-provided business card')" \
    "INSERT INTO rl_social_accounts (person_key, platform, handle) VALUES ('shiro-sample', 'github', 'example-shiro')" \
    "INSERT INTO rl_interaction_notes (person_key, kind, note) VALUES ('shiro-sample', 'rumor', 'n')")
row 'a transaction with a failing statement returns an error' "$(yesno grep -q '^ERROR' <<<"$out")" 'yes'
row '... and leaves neither the person nor the account' "$(val "SELECT (SELECT count(*) FROM rl_people WHERE person_key = 'shiro-sample') + (SELECT count(*) FROM rl_social_accounts WHERE handle = 'example-shiro')")" '0'
out=$(python3 "$CALL" --tx "BEGIN" "INSERT INTO rl_people (person_key, display_name) VALUES ('goro-sample', 'Goro Sample')")
row 'a transaction that tries to control the transaction itself is refused' "$(yesno grep -q '^ERROR' <<<"$out")" 'yes'
row '... before running anything' "$(val "SELECT count(*) FROM rl_people WHERE person_key = 'goro-sample'")" '0'
row 'the intake leaves one meeting, one context and one task note' "$(val "SELECT count(*) || '-' || count(DISTINCT kind) || '-' || sum(CASE WHEN kind IN ('meeting', 'context', 'task') THEN 1 ELSE 0 END) FROM rl_interaction_notes WHERE person_key = 'saburo-sample'")" '3-3-3'
row 'rl_v_people shows when they met' "$(val "SELECT last_met_at FROM rl_v_people WHERE person_key = 'saburo-sample'")" '2026-06-10'
# last_met_at compares meeting times in UTC: 23:30 at -08:00 is later than 09:00 at +09:00 the next calendar day
sql "INSERT INTO rl_interaction_notes (person_key, kind, note, occurred_at) VALUES ('saburo-sample', 'meeting', 'event: Example Meetup #4', '2026-11-28T09:00:00+09:00')" \
    "INSERT INTO rl_interaction_notes (person_key, kind, note, occurred_at) VALUES ('saburo-sample', 'meeting', 'event: Example Meetup #5', '2026-11-27T23:30:00-08:00')" >/dev/null
row 'the latest meeting is chosen by its time in UTC, not by its text' "$(yesno [ "$(val "SELECT last_met_at FROM rl_v_people WHERE person_key = 'saburo-sample'")" = 2026-11-27T23:30:00-08:00 ])" 'yes'

