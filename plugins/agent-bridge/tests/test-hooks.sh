#!/bin/bash
# The hooks: the background poller that wakes Claude (exit 2) and the unread count added to a prompt.
set -u
. "$(dirname "$0")/lib.sh"
WAIT="$PLUGIN/hooks/wait_inbox.py"
NOTICE="$PLUGIN/hooks/unread_notice.py"

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

# First poll records the newest id without waking; a message sent meanwhile wakes it at the next poll
input s1 | python3 "$WAIT" 2>"$CLAUDE_PLUGIN_DATA/stderr" & poller=$!
sleep 2
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

out=$(echo '{}' | python3 "$NOTICE")
row 'the prompt hook adds the unread count as context' "$(yesno [ "$(jget "$out" 'd["hookSpecificOutput"]["additionalContext"].split(":")[1].split()[0]')" = 1 ])" yes
row 'the prompt context never carries the message body' "$(yesno not grep -q 'secret-looking' <<<"$out")" yes
id=$(jget "$(post tok-claude '{"action":"inbox"}')" 'd["messages"][0]["id"]')
post tok-claude "{\"action\":\"ack\",\"ids\":[$id]}" >/dev/null
row 'with nothing unread the prompt hook prints nothing' "$(yesno [ -z "$(echo '{}' | python3 "$NOTICE")" ])" yes
stop_fake

start_fake FAKE_BRIDGE_DOWN=1
export CLAUDE_PLUGIN_OPTION_BRIDGE_URL="$BRIDGE_URL"
out=$(echo '{}' | python3 "$NOTICE"); rc=$?
row 'a failing bridge makes the prompt hook silent with exit 0' "$(yesno [ "$rc" = 0 ] && [ -z "$out" ])" yes
stop_fake
rm -rf "$CLAUDE_PLUGIN_DATA"
