#!/bin/bash
# Shared helpers for test-*.sh: a fake bridge on a local port, the MCP driver, and the row format run-all.sh reads.
TESTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(dirname "$TESTS")"
CALL="$TESTS/mcp_call.py"
CONTRACT="$TESTS/fixtures/contract.json"
# Fake participant credentials the fake bridge accepts (test data only)
FAKE_CLAUDE=tok-claude
FAKE_WRONG=not-a-participant

# start_fake [ENV=VALUE ...]: start the fake bridge with agents alpha, beta and claude; sets BRIDGE_URL
start_fake() {
  local portfile; portfile=$(mktemp "${TMPDIR:-/tmp}/agent-bridge-port.XXXXXX")
  : > "$portfile"
  env FAKE_BRIDGE_AGENTS="claude=tok-claude,alpha=tok-alpha,beta=tok-beta" "$@" python3 "$TESTS/fake_bridge.py" "$portfile" &
  FAKE_PID=$!
  # A cold python3 on a CI runner can take several seconds to start; give it 60
  for _ in $(seq 600); do [ -s "$portfile" ] && break; sleep 0.1; done
  local port; port=$(cat "$portfile"); rm -f "$portfile"
  [ -n "$port" ] || { echo "fake bridge did not start"; exit 1; }
  BRIDGE_URL="http://127.0.0.1:$port/functions/v1/agent-bridge"
}
stop_fake() { kill "$FAKE_PID" 2>/dev/null; wait "$FAKE_PID" 2>/dev/null; }

# post AS_TOKEN JSON: one POST to the fake bridge, prints the response body
post() {
  python3 - "$BRIDGE_URL" "$1" "$2" <<'PY'
import sys, urllib.request, urllib.error
req = urllib.request.Request(sys.argv[1], data=sys.argv[3].encode(), method="POST",
                             headers={"Authorization": "Bearer " + sys.argv[2], "Content-Type": "application/json"})
try:
    print(urllib.request.urlopen(req).read().decode())
except urllib.error.HTTPError as e:
    print(e.read().decode())
PY
}

# keys_match KIND JSON: the JSON object's keys are exactly contract.json's list for KIND
keys_match() {
  python3 - "$CONTRACT" "$1" "$2" <<'PY'
import json, sys
want = sorted(json.load(open(sys.argv[1]))[sys.argv[2]])
sys.exit(0 if sorted(json.loads(sys.argv[3])) == want else 1)
PY
}

# jget JSON EXPR: evaluate a Python expression over the parsed JSON as d (EXPR is always written in these test files)
jget() { python3 -c 'import json, sys; d = json.loads(sys.argv[1]); print(eval(sys.argv[2]))' "$1" "$2"; }

not() { ! "$@"; }
yesno() { if "$@"; then echo yes; else echo no; fi; }
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }
