#!/bin/bash
# Checks for hooks/decision-capture.py with the regex judge (nothing leaves the machine). State goes to a temp
# directory through DECISION_CAPTURE_STATE_DIR. The replies are closing lines of real replies from the labelled set
# (tests/fixtures/decision-capture/ask_dataset.json), shortened.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/decision-capture.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/decision-capture.XXXX")
trap 'rm -rf "$T"' EXIT
export DECISION_CAPTURE_STATE_DIR="$T/state"
export CLAUDE_PLUGIN_OPTION_DECISION_CAPTURE=enforce CLAUDE_PLUGIN_OPTION_DECISION_JUDGE=regex
unset CLAUDE_PLUGIN_OPTION_DECISION_REGISTER_COMMAND CLAUDE_PLUGIN_OPTION_DECISION_STOP_LIMIT
# keys from the caller's environment would make the model-judge rows below call the vendor
unset CLAUDE_PLUGIN_OPTION_DECISION_OPENAI_API_KEY CLAUDE_PLUGIN_OPTION_DECISION_TYPESAFE_API_KEY \
  CLAUDE_PLUGIN_OPTION_DECISION_GOOGLE_API_KEY

ASK=$'## 次の一手\n\n| 案 | 中身 |\n|---|---|\n| A | 設定を分ける |\n| B | 1 つにまとめる |\n\nA で進めてよいですか？'
REPORT=$'## 結果\n\nPR を作成し、CI は全部通りました。レビュー待ちです。'

# ev <event> <session> [json fields...]: send one hook event, print block|pass
ev() {
  python3 - "$@" <<'PY' | python3 "$HOOK" > "$T/out" 2>"$T/err"
import json, sys
ev, sid, *kv = sys.argv[1:]
d = {"hook_event_name": ev, "session_id": sid, "cwd": "/work/repo"}
for pair in kv:
    k, v = pair.split("=", 1)
    d[k] = json.loads(v)
print(json.dumps(d))
PY
  grep -q '"decision": "block"' "$T/out" && echo block || echo pass
}
msg() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
stop() { ev Stop "$1" "last_assistant_message=$(msg "$2")" "stop_hook_active=${3:-false}"; }

echo '=== a prose question blocks once ==='
ev UserPromptSubmit s1 >/dev/null
r=$(stop s1 "$ASK"); echo "  first Stop -> $r (expect block)"
grep -q 'AskUserQuestion' "$T/out" && x=ok || x=ng; echo "  the reason offers AskUserQuestion -> $x (expect ok)"
grep -q 'dismiss --session' "$T/out" && x=ok || x=ng; echo "  the reason gives the dismiss command -> $x (expect ok)"
r=$(stop s1 "$ASK" true); echo "  second Stop with stop_hook_active -> $r (expect pass)"
r=$(stop s1 "$ASK"); echo "  another Stop in the same turn -> $r (expect pass)"
ev UserPromptSubmit s1 >/dev/null
r=$(stop s1 "$ASK"); echo "  next turn, same question -> $r (expect block)"

echo '=== a report does not block ==='
ev UserPromptSubmit s2 >/dev/null
r=$(stop s2 "$REPORT"); echo "  report -> $r (expect pass)"
r=$(stop s2 '{"status": "ok", "next": "どちらにしますか？"}'); echo "  JSON-only reply -> $r (expect pass)"

echo '=== a turn that used AskUserQuestion passes ==='
ev UserPromptSubmit s3 >/dev/null
ev PostToolUse s3 'tool_name="AskUserQuestion"' 'tool_input={"questions": []}' >/dev/null
r=$(stop s3 "$ASK"); echo "  Stop after AskUserQuestion -> $r (expect pass)"

echo '=== a turn that ran the registration command passes ==='
export CLAUDE_PLUGIN_OPTION_DECISION_REGISTER_COMMAND='tracker decisions add --key {key} --decision {decision}'
ev UserPromptSubmit s4 >/dev/null
r=$(stop s4 "$ASK"); grep -q 'tracker decisions add' "$T/out" && x=ok || x=ng
echo "  without it -> $r (expect block)"; echo "  the reason shows the template -> $x (expect ok)"
ev UserPromptSubmit s4 >/dev/null
ev PostToolUse s4 'tool_name="Bash"' 'tool_input={"command": "tracker  decisions add --key db_split --decision \"Split the config?\""}' >/dev/null
r=$(stop s4 "$ASK"); echo "  after the registration command -> $r (expect pass)"
ev UserPromptSubmit s4 >/dev/null
ev PostToolUse s4 'tool_name="Bash"' 'tool_input={"command": "tracker decisions list"}' >/dev/null
r=$(stop s4 "$ASK"); echo "  another command of the same tool -> $r (expect block)"
ev UserPromptSubmit s4 >/dev/null
ev PostToolUse s4 'tool_name="Bash"' 'tool_input={"command": "tracker decisions add --key db_split --decision x", "run_in_background": true}' >/dev/null
r=$(stop s4 "$ASK"); echo "  the registration command started in the background -> $r (expect block)"
unset CLAUDE_PLUGIN_OPTION_DECISION_REGISTER_COMMAND

echo '=== modes ==='
r=$(CLAUDE_PLUGIN_OPTION_DECISION_CAPTURE=off stop s5 "$ASK"); echo "  off -> $r (expect pass)"
[ -e "$T/state/s5.json" ] && x=written || x=none; echo "  off writes state -> $x (expect none)"
r=$(CLAUDE_PLUGIN_OPTION_DECISION_CAPTURE=observe stop s6 "$ASK"); echo "  observe -> $r (expect pass)"
n=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1])).get("judged", [])))' "$T/state/s6.json" 2>/dev/null)
echo "  observe records the would-be block -> ${n:-0} (expect 1)"

echo '=== dismissals in a row stop the blocking ==='
export CLAUDE_PLUGIN_OPTION_DECISION_STOP_LIMIT=2
for i in 1 2; do
  ev UserPromptSubmit s7 >/dev/null; stop s7 "$ASK" >/dev/null
  python3 "$HOOK" dismiss --session s7 --why "a report, not a question" >/dev/null 2>&1
done
ev UserPromptSubmit s7 >/dev/null
r=$(stop s7 "$ASK"); echo "  after 2 dismissals with limit 2 -> $r (expect pass)"
ev PostToolUse s7 'tool_name="AskUserQuestion"' 'tool_input={}' >/dev/null
ev UserPromptSubmit s7 >/dev/null
r=$(stop s7 "$ASK"); echo "  after AskUserQuestion resets the count -> $r (expect block)"
unset CLAUDE_PLUGIN_OPTION_DECISION_STOP_LIMIT
python3 "$HOOK" dismiss --session s7 >/dev/null 2>&1; c=$?; echo "  dismiss without --why, exit code -> $c (expect 2)"

echo '=== a model judge without a key falls back to regex ==='
ev UserPromptSubmit s8 >/dev/null
r=$(CLAUDE_PLUGIN_OPTION_DECISION_JUDGE=google stop s8 "$ASK"); echo "  google, no key -> $r (expect block)"
grep -q 'fell back from google: no API key' "$T/out" && x=ok || x=ng; echo "  the reason says it fell back -> $x (expect ok)"
ev UserPromptSubmit s9 >/dev/null
r=$(CLAUDE_PLUGIN_OPTION_DECISION_JUDGE=google stop s9 'Please pick a deployment region.')
echo "  google, no key, a request with no question mark -> $r (expect block)"

echo '=== a malformed model response falls back to regex ==='
python3 - "$(dirname "$HOOK")" <<'PY' || exit 1
import sys
sys.path.insert(0, sys.argv[1])
import _decision_judge as j
for backend, res in (("openai", {"answers": [None]}), ("google", {"answers": {"kind": None}})):
    j._post = lambda *a, res=res, **k: res
    try:
        r = "fallback" if j.asks_decision("Which do you prefer, A or B?", backend, key="k").fell_back else "none"
    except Exception as e:
        r = type(e).__name__
    print(f"  {backend} answer is null -> {r} (expect fallback)")
PY

echo '=== the hook never fails the turn ==='
echo 'not json' | python3 "$HOOK" >/dev/null 2>&1; c=$?; echo "  broken input, exit code -> $c (expect 0)"
