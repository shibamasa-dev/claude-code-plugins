#!/bin/bash
# The hooks: the background poller that wakes Claude (exit 2) and the unread count added to a prompt.
set -u
. "$(dirname "$0")/lib.sh"
WAIT="$PLUGIN/hooks/wait_inbox.py"
NOTICE="$PLUGIN/hooks/unread_notice.py"
ARM="$PLUGIN/hooks/arm_session.py"

export CLAUDE_PLUGIN_DATA; CLAUDE_PLUGIN_DATA=$(mktemp -d "${TMPDIR:-/tmp}/agent-bridge-hooks.XXXXXX")
unset CLAUDE_PLUGIN_OPTION_BRIDGE_URL CLAUDE_PLUGIN_OPTION_AGENT_ID CLAUDE_PLUGIN_OPTION_LISTEN
input() { printf '{"session_id":"%s","hook_event_name":"Stop"}' "$1"; }

# wait_status SESSION: run the poller (short interval and deadline); print its exit code
wait_status() { input "$1" | python3 "$WAIT" 2>"$CLAUDE_PLUGIN_DATA/stderr"; echo $?; }

start_fake
export CLAUDE_PLUGIN_OPTION_BRIDGE_URL="$BRIDGE_URL" CLAUDE_PLUGIN_OPTION_AGENT_ID=claude
export CLAUDE_PLUGIN_OPTION_POLL_SECONDS=15 CLAUDE_PLUGIN_OPTION_MAX_WAIT_MINUTES=1

row 'with listen off the poller exits at once' "$(yesno [ "$(CLAUDE_PLUGIN_OPTION_LISTEN=false wait_status s1)" = 0 ])" yes
export CLAUDE_PLUGIN_OPTION_LISTEN=true
row 'with listen on but no bridge_url the poller exits at once' "$(yesno [ "$(CLAUDE_PLUGIN_OPTION_BRIDGE_URL= wait_status s1)" = 0 ])" yes
row 'a bridge_url that only starts with http://127.0.0.1 is not trusted' "$(yesno [ "$(echo '{}' | CLAUDE_PLUGIN_OPTION_BRIDGE_URL=http://127.0.0.1.example.test/x python3 "$NOTICE")" = '' ])" yes
# Both conditions go into one test so yesno sees them together (yesno [ a ] && [ b ] would print before b runs)
row 'a session that never used a bridge tool does not poll' "$(yesno [ "$(wait_status s1)/$(ls "$CLAUDE_PLUGIN_DATA/wait/s1.pid" 2>/dev/null)" = 0/ ])" yes
input s1 | python3 "$ARM"
row 'using a bridge tool marks the session' "$(yesno [ -e "$CLAUDE_PLUGIN_DATA/wait/s1.armed" ])" yes

# First poll records the newest id without waking; a message sent meanwhile wakes it at the next poll
input s1 | python3 "$WAIT" 2>"$CLAUDE_PLUGIN_DATA/stderr" & poller=$!
for _ in $(seq 100); do ls "$CLAUDE_PLUGIN_DATA"/wait/claude-*.seen >/dev/null 2>&1 && break; sleep 0.1; done  # first poll done
post tok-alpha '{"action":"send","to":"claude","thread":"t1","body":"secret-looking body text"}' >/dev/null
second=$(input s1 | python3 "$WAIT" 2>/dev/null; echo $?)
row 'a second poller for the same session exits at once' "$(yesno [ "$second" = 0 ])" yes
wait "$poller"; rc=$?
row 'a new message wakes Claude with exit 2' "$(yesno [ "$rc" = 2 ])" yes
row 'the wake text gives a count and the tool to call' "$(yesno grep -q "for 'claude' (1 unread). Call check_inbox" "$CLAUDE_PLUGIN_DATA/stderr")" yes
row 'the wake text never carries the message body' "$(yesno not grep -q 'secret-looking' "$CLAUDE_PLUGIN_DATA/stderr")" yes
row 'the poller removes its pid file when it ends' "$(yesno [ ! -e "$CLAUDE_PLUGIN_DATA/wait/s1.pid" ])" yes

# The same message, still unread, must not wake the next poller (no wake loop after every turn)
start=$(date +%s)
rc=$(CLAUDE_PLUGIN_OPTION_MAX_WAIT_MINUTES=1 wait_status s1)
row 'an unread message already seen does not wake again; the poller ends at its deadline' "$(yesno [ "$rc" = 0 ])" yes
row 'and it waited for the deadline rather than exiting early' "$(yesno [ $(( $(date +%s) - start )) -ge 55 ])" yes

# A reply that arrived before this machine's first poll (no seen id yet) still wakes the session
rm -f "$CLAUDE_PLUGIN_DATA"/wait/claude-*.seen
row 'an unread reply that landed before the first poll wakes Claude' "$(yesno [ "$(wait_status s1)" = 2 ])" yes
seen_rule() {  # polls LATEST:UNREAD ... through advance_seen on a fresh directory: the last decision and stored latest id
  python3 - "$PLUGIN/hooks" "$@" <<'PY2'
import json, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import wait_inbox
d = Path(tempfile.mkdtemp())
for poll in sys.argv[2:]:
    latest, unread = map(int, poll.split(":"))
    woke = wait_inbox.advance_seen(d, "x", latest, unread)
print(woke, json.loads((d / "x.seen").read_text())["latest"])
shutil.rmtree(d)
PY2
}
row 'with every message already read, a newer id is recorded without waking' "$(yesno [ "$(seen_rule 5:0)" = 'False 5' ])" yes
row 'a message that commits after a newer one (lower id, unread count rises) still wakes' "$(yesno [ "$(seen_rule 5:1 5:2)" = 'True 5' ])" yes
row 'the same unread count with no newer id does not wake again' "$(yesno [ "$(seen_rule 5:1 5:1)" = 'False 5' ])" yes
row 'two bridges with the same agent id keep separate seen state' "$(yesno not [ "$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import wait_inbox as w; print(w.seen_key("https://a.example/f?agent=claude", "claude") == w.seen_key("https://b.example/f?agent=claude", "claude"))' "$PLUGIN/hooks")" = True ])" yes

out=$(echo '{}' | python3 "$NOTICE")
row 'the prompt hook adds the unread count as context' "$(yesno [ "$(jget "$out" 'd["hookSpecificOutput"]["additionalContext"].split(":")[1].split()[0]')" = 1 ])" yes
row 'the prompt context never carries the message body' "$(yesno not grep -q 'secret-looking' <<<"$out")" yes
id=$(jget "$(post tok-claude '{"action":"inbox"}')" 'd["messages"][0]["id"]')
post tok-claude "{\"action\":\"ack\",\"ids\":[$id]}" >/dev/null
row 'with nothing unread the prompt hook prints nothing' "$(yesno [ -z "$(echo '{}' | python3 "$NOTICE")" ])" yes

# The wait counts from the session's last turn: a new turn's hook refreshes the turn file the running poller reads
input s1 | python3 "$WAIT" 2>/dev/null & poller=$!
for _ in $(seq 100); do [ -e "$CLAUDE_PLUGIN_DATA/wait/s1.pid" ] && break; sleep 0.1; done
python3 -c 'import os, sys, time; t = time.time() - 600; os.utime(sys.argv[1], (t, t))' "$CLAUDE_PLUGIN_DATA/wait/s1.turn"
input s1 | python3 "$WAIT" 2>/dev/null
row 'a new turn while a poller runs moves its deadline to max_wait_minutes from now' "$(yesno python3 -c 'import os, sys, time; sys.exit(time.time() - os.stat(sys.argv[1]).st_mtime > 5)' "$CLAUDE_PLUGIN_DATA/wait/s1.turn")" yes
python3 -c 'import os, sys, time; t = time.time() - 120; os.utime(sys.argv[1], (t, t))' "$CLAUDE_PLUGIN_DATA/wait/s1.turn"
for _ in $(seq 250); do kill -0 "$poller" 2>/dev/null || break; sleep 0.1; done
row 'a running poller ends once the last turn is older than max_wait_minutes' "$(yesno not kill -0 "$poller" 2>/dev/null)" yes
kill "$poller" 2>/dev/null; wait "$poller" 2>/dev/null
stop_fake

start_fake FAKE_BRIDGE_DOWN=1
export CLAUDE_PLUGIN_OPTION_BRIDGE_URL="$BRIDGE_URL"
out=$(echo '{}' | python3 "$NOTICE"); rc=$?
row 'a failing bridge makes the prompt hook silent with exit 0' "$(yesno [ "$rc/$out" = 0/ ])" yes
stop_fake
rm -rf "$CLAUDE_PLUGIN_DATA"
