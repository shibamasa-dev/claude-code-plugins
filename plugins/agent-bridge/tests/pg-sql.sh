#!/bin/bash
# The schema's rules on a real Postgres (with Supabase stand-ins for vault and net). Run by run-postgres.sh,
# which sets AGENT_BRIDGE_PG_URL to an empty database.
set -u
. "$(dirname "$0")/lib.sh"
URL=${AGENT_BRIDGE_PG_URL:?run this through run-postgres.sh}
MIGRATION="$PLUGIN/bridge/migrations/0001_init.sql"

q() { psql "$URL" -X -q -t -A -v ON_ERROR_STOP=1 -c "$1"; }
# err SQL: the error code the statement raised ("none" when it succeeded)
err() { local e; e=$(psql "$URL" -X -q -t -A -v ON_ERROR_STOP=1 -c "$1" 2>&1 >/dev/null) && { echo none; return; }
        sed -n 's/^ERROR: *\([a-z_]*\):.*/\1/p' <<<"$e" | head -1; }
api() { q "SELECT agent_bridge.api('$1', '$2', '$3'::jsonb)"; }
set_secret() { q "UPDATE vault.secrets SET secret = '$2' WHERE name = '$1'"; }

psql "$URL" -X -q -v ON_ERROR_STOP=1 -f "$TESTS/fixtures/supabase_stubs.sql" >/dev/null || exit 1
row 'the migration applies' "$(yesno psql "$URL" -X -q -v ON_ERROR_STOP=1 -f "$MIGRATION")" yes
row 'and applies again without error (idempotent)' "$(yesno psql "$URL" -X -q -v ON_ERROR_STOP=1 -f "$MIGRATION")" yes
row 'the API roles get no use of the schema' "$(q "SELECT has_schema_privilege('anon', 'agent_bridge', 'USAGE') OR has_schema_privilege('authenticated', 'agent_bridge', 'USAGE')")" f

q "SELECT agent_bridge.register_participant('claude', 'poll', 'Claude Code', 'coordinator', 'code')" >/dev/null
q "SELECT agent_bridge.register_participant('alpha', 'webhook', 'Alpha', 'research', 'web research')" >/dev/null
q "SELECT agent_bridge.register_participant('beta', 'poll', 'Beta', 'review', 'review')" >/dev/null
row 'registering creates every secret as a placeholder' "$(q "SELECT string_agg(DISTINCT state, ',') FROM agent_bridge.doctor()")" placeholder
row 'a webhook agent gets a token, a webhook url and a webhook key' "$(yesno [ "$(q "SELECT count(*) FROM agent_bridge.doctor() WHERE agent_id = 'alpha'")" = 3 ])" yes
row 'doctor never returns a secret value' "$(yesno not grep -q REPLACE_ME <<<"$(q "SELECT * FROM agent_bridge.doctor()")")" yes
row 'the placeholder token authenticates no one' "$(err "SELECT agent_bridge.api('REPLACE_ME', 'participants')")" unauthorized
row 'an empty token authenticates no one' "$(err "SELECT agent_bridge.api('', 'participants')")" unauthorized

set_secret 'agent_bridge:claude:token' tok-claude
set_secret 'agent_bridge:beta:token' tok-beta
set_secret 'agent_bridge:alpha:token' tok-alpha
q "SELECT agent_bridge.register_participant('claude', 'poll', 'Claude Code', 'coordinator', 'code')" >/dev/null
row 'running setup again keeps a secret the user replaced' "$(q "SELECT state FROM agent_bridge.doctor() WHERE secret_name = 'agent_bridge:claude:token'")" set
out=$(api tok-claude participants '{}')
row 'a real token identifies its agent' "$(jget "$out" 'd["me"]')" claude
row 'participants answers with the contract keys' "$(yesno keys_match participants "$out")" yes
row 'each participant has the contract keys' "$(yesno keys_match participant "$(jget "$out" 'json.dumps(d["participants"][0])')")" yes

out=$(api tok-claude send '{"to":"alpha","thread":"plan","body":"First question","purpose":"plan review"}')
row 'send answers with the contract keys' "$(yesno keys_match send "$out")" yes
row 'a webhook agent with placeholder secrets is stored as not_configured' "$(jget "$out" 'd["delivery"]')" not_configured
row 'and nothing is POSTed' "$(yesno [ "$(q 'SELECT count(*) FROM net.calls')" = 0 ])" yes

set_secret 'agent_bridge:alpha:webhook_url' 'https://hooks.example.test/alpha'
set_secret 'agent_bridge:alpha:webhook_key' 'key-alpha'
out=$(api tok-claude send '{"to":"alpha","thread":"plan","body":"Second question"}')
row 'with real webhook secrets the message is queued' "$(jget "$out" 'd["delivery"]')" queued
row 'the POST goes to the stored URL with the stored key as a bearer token' \
  "$(q "SELECT url = 'https://hooks.example.test/alpha' AND headers ->> 'Authorization' = 'Bearer key-alpha' FROM net.calls")" t
row 'the POST body carries the message and its thread' "$(q "SELECT body ->> 'body' = 'Second question' AND body ->> 'thread' = 'plan' AND body ->> 'from' = 'claude' FROM net.calls")" t
mid=$(jget "$out" 'd["id"]')
out=$(api tok-claude message "{\"id\":$mid}")
row 'message status answers with the contract keys plus the webhook fields' "$(yesno keys_match message "$(jget "$out" 'json.dumps({k: v for k, v in d.items() if not k.startswith("webhook_")})')")" yes
row 'before a response is recorded the status says so' "$(yesno grep -q 'no response recorded yet' <<<"$out")" yes
q "INSERT INTO net._http_response (id, status_code) SELECT request_id, 502 FROM agent_bridge.messages WHERE id = $mid"
row 'a failed delivery shows the HTTP status the service returned' "$(yesno [ "$(jget "$(api tok-claude message "{\"id\":$mid}")" 'd["webhook_status"]')" = 502 ])" yes
row 'an agent outside the conversation cannot look the message up' "$(err "SELECT agent_bridge.api('tok-beta', 'message', '{\"id\":$mid}')")" not_found

api tok-beta send '{"to":"claude","thread":"notes","body":"note one"}' >/dev/null
api tok-beta send '{"to":"claude","thread":"notes","body":"note two"}' >/dev/null
st=$(q "SELECT agent_bridge.status('claude')")
row 'status answers with the contract keys' "$(yesno keys_match status "$st")" yes
row 'status counts the unread messages' "$(yesno [ "$(jget "$st" 'd["unread"]')" = 2 ])" yes
first=$(api tok-claude inbox '{"limit":1}')
row 'inbox answers with the contract keys' "$(yesno keys_match inbox "$first")" yes
row 'each inbox message has the contract keys' "$(yesno keys_match inbox_message "$(jget "$first" 'json.dumps(d["messages"][0])')")" yes
second=$(api tok-claude inbox '{}')
row 'a claimed message is not handed out again (a second reader gets the other one)' \
  "$(yesno [ "$(jget "$second" '[m["body"] for m in d["messages"]]')" = "['note two']" ])" yes
row 'claimed messages still count as unread until acked' "$(yesno [ "$(jget "$(q "SELECT agent_bridge.status('claude')")" 'd["unread"]')" = 2 ])" yes
ids=$(jget "$first" '[m["id"] for m in d["messages"]]')
row 'an agent cannot ack a message addressed to someone else' "$(yesno [ "$(jget "$(api tok-beta ack "{\"ids\":$ids}")" 'd["acked"]')" = 0 ])" yes
out=$(api tok-claude ack "{\"ids\":$ids}")
row 'ack answers with the contract keys' "$(yesno keys_match ack "$out")" yes
row 'the recipient acks it' "$(yesno [ "$(jget "$out" 'd["acked"]')" = 1 ])" yes
q "UPDATE agent_bridge.messages SET claimed_at = now() - interval '11 minutes' WHERE body = 'note two'"
row 'a claim older than 10 minutes is handed out again' "$(yesno [ "$(jget "$(api tok-claude inbox '{}')" 'd["messages"][0]["body"]')" = 'note two' ])" yes
row 'the inbox only ever shows messages addressed to the caller' \
  "$(yesno [ "$(jget "$(api tok-alpha inbox '{}')" 'sorted({m["from"] for m in d["messages"]})')" = "['claude']" ])" yes

q "UPDATE agent_bridge.threads SET max_messages = 3 WHERE thread_id = 'plan'"
api tok-alpha send '{"to":"claude","thread":"plan","body":"Third"}' >/dev/null
row 'past max_messages a send is refused with hop_limit' "$(err "SELECT agent_bridge.api('tok-claude', 'send', '{\"to\":\"alpha\",\"thread\":\"plan\",\"body\":\"Fourth\"}')")" hop_limit
row 'the cap also holds for a direct INSERT' \
  "$(err "INSERT INTO agent_bridge.messages (thread_id, from_agent, to_agent, body, delivery) VALUES ('plan', 'beta', 'claude', 'x', 'poll')")" hop_limit
q "UPDATE agent_bridge.threads SET status = 'closed' WHERE thread_id = 'notes'"
row 'a closed thread takes no more messages' "$(err "SELECT agent_bridge.api('tok-beta', 'send', '{\"to\":\"claude\",\"thread\":\"notes\",\"body\":\"late\"}')")" thread_closed
row 'sending to an unknown agent is refused' "$(err "SELECT agent_bridge.api('tok-beta', 'send', '{\"to\":\"nobody\",\"thread\":\"x\",\"body\":\"hi\"}')")" unknown_agent
row 'an agent cannot message itself' "$(err "SELECT agent_bridge.api('tok-beta', 'send', '{\"to\":\"beta\",\"thread\":\"self\",\"body\":\"hi\"}')")" bad_request
row 'a thread id outside the pattern is a bad_request' "$(err "SELECT agent_bridge.api('tok-beta', 'send', '{\"to\":\"claude\",\"thread\":\"Bad Thread\",\"body\":\"hi\"}')")" bad_request
row 'a body over 20000 characters is a bad_request' "$(err "SELECT agent_bridge.api('tok-beta', 'send', jsonb_build_object('to', 'claude', 'thread', 'long', 'body', repeat('x', 20001)))")" bad_request
row 'a non-integer limit is a bad_request' "$(err "SELECT agent_bridge.api('tok-beta', 'inbox', '{\"limit\":\"ten\"}')")" bad_request
row 'non-integer ids in ack are a bad_request' "$(err "SELECT agent_bridge.api('tok-beta', 'ack', '{\"ids\":[\"x\"]}')")" bad_request
row 'a missing message id is a bad_request' "$(err "SELECT agent_bridge.api('tok-beta', 'message', '{}')")" bad_request
row 'an agent that is not in a thread cannot write to it' "$(err "SELECT agent_bridge.api('tok-beta', 'send', '{\"to\":\"alpha\",\"thread\":\"plan\",\"body\":\"butting in\"}')")" not_found
row 'and the refused write stores nothing' "$(q "SELECT count(*) FROM agent_bridge.messages WHERE thread_id = 'plan' AND from_agent = 'beta'")" 0
api tok-claude send '{"to":"beta","thread":"invite","body":"join us"}' >/dev/null
row 'an agent that received a message in a thread can answer in it' "$(jget "$(api tok-beta send '{"to":"claude","thread":"invite","body":"joined"}')" 'd["delivery"]')" poll
row 'an unknown action is a bad_request' "$(err "SELECT agent_bridge.api('tok-beta', 'delete_all')")" bad_request

before=$(q "SELECT updated_at FROM agent_bridge.participants WHERE agent_id = 'beta'")
sleep 1
q "UPDATE agent_bridge.participants SET role = 'reviewer' WHERE agent_id = 'beta'"
row 'updated_at moves on an UPDATE that leaves it out' "$(yesno [ "$(q "SELECT updated_at FROM agent_bridge.participants WHERE agent_id = 'beta'")" != "$before" ])" yes
