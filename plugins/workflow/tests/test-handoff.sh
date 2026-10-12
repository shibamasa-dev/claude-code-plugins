#!/bin/bash
# Regression test for multiple handoffs per project in handoff.py (2026-09-25): parallel sessions must not overwrite each other's entries.
# Background: it used to keep one entry per project and overwrite it, so a session closed later
#             silently erased another session's handoff.
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/handoff.py"
export HANDOFF_STATE_DIR=$(mktemp -d /tmp/handoff-test-state.XXXX)
REPO=$(mktemp -d /tmp/handoff-test-repo.XXXX)
(cd "$REPO" && git init -q . && git remote add origin git@github.com:example-org/handoff-test.git)

cnt() { python3 - "$HANDOFF_STATE_DIR" <<'PY'
import glob, json, sys
fs = glob.glob(sys.argv[1] + "/*.json")
n = len(json.load(open(fs[0]))["items"]) if fs else 0
print({0: "zero", 1: "one", 2: "two"}.get(n, "many"))
PY
}
rc() { (cd "$REPO" && python3 "$H" "$@" >/dev/null 2>&1) && echo ok || echo refuse; }
row() { printf '  %-52s -> %-5s (expect %s)\n' "$1" "$2" "$3"; }

echo '=== add / update ==='
rc write --entry example-org/handoff-test#1 --state s1 --next n1 >/dev/null
row 'write A' "$(cnt)" one
rc write --entry example-org/handoff-test#2 --state s2 --next n2 >/dev/null
row 'write another entry B (appended)' "$(cnt)" two
rc write --entry example-org/handoff-test#1 --state s1b --next n1b >/dev/null
row 'rewrite the same entry A (count stays)' "$(cnt)" two
got=$(cd "$REPO" && python3 "$H" show | grep -q 's1b' && ! (cd "$REPO" && python3 "$H" show | grep -q 'state: s1$') && echo ok || echo bad)
row 'A now holds the new values' "$got" ok

echo '=== SessionStart injects all entries ==='
got=$(printf '{"hook_event_name":"SessionStart","source":"startup","cwd":"%s"}' "$REPO" | python3 "$H" \
      | grep -c 'handoff-test#' | awk '{print ($1==2)?"two":"bad"}')
row 'startup shows both entries' "$got" two

echo '=== consume ==='
row 'consume without --entry is refused when there are several' "$(rc consume)" refuse
row 'consume of an unknown entry is refused' "$(rc consume --entry example-org/handoff-test#9)" refuse
rc consume --entry example-org/handoff-test#1 >/dev/null
row 'consume --entry A removes only A' "$(cnt)" one
row 'with one entry left, consume works without --entry' "$(rc consume)" ok
row 'removing the last entry removes the file' "$(cnt)" zero

echo '=== entry for another repo ==='
row 'an entry for another repo is not written' "$(rc write --entry example-org/other#1 --state s --next n)" refuse
row '--force writes it' "$(rc write --entry example-org/other#1 --state s --next n --force)" ok

echo '=== the injected consume command runs as printed ==='
cmd=$(printf '{"hook_event_name":"SessionStart","source":"startup","cwd":"%s"}' "$REPO" | python3 "$H" \
      | sed -n 's/.*`\(python3 .* consume --entry <entry>\)`.*/\1/p')
row 'the injected text names the hook script' "$([[ "$cmd" == "python3 \"$H\" consume "* ]] && echo ok || echo bad)" ok
(cd "$REPO" && sh -c "${cmd/<entry>/example-org/other#1}" >/dev/null)
row 'running it removes that entry' "$(cnt)" zero

rm -rf "$HANDOFF_STATE_DIR" "$REPO"
