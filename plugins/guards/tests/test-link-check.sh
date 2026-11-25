#!/bin/bash
# Measure link-check.py (Stop hook): which file links in the last reply make it block Stop.
# Synthetic session folders under a temp dir: a working directory, a scratchpad, an added directory (listed in a
# fake transcript's environment entry) and a folder outside all of them.
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/link-check.py"
T0=${TMPDIR:-/tmp}; W=$(mktemp -d "${T0%/}/link-check.XXXX")
W=$(cd "$W" && pwd -P)
export WORK="$W/work" SCRATCH="$W/scratch" ADDED="$W/added" OUTSIDE="$W/outside"
mkdir -p "$WORK/docs" "$SCRATCH" "$ADDED" "$OUTSIDE"
: > "$WORK/docs/a.md"; : > "$WORK/docs/a (1).md"; : > "$SCRATCH/out.png"; : > "$ADDED/notes.md"; : > "$OUTSIDE/runbook.md"
export TRANSCRIPT="$W/t.jsonl" BARE="$W/bare.jsonl"
python3 - <<'PY'
import json, os
env = {"type": "attachment", "attachment": {"type": "environment", "snapshot": {
    "workingDirectory": os.environ["WORK"], "additionalWorkingDirectories": [os.environ["ADDED"]],
    "scratchpadDirectory": os.environ["SCRATCH"]}}}
with open(os.environ["TRANSCRIPT"], "w") as f:
    f.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n" + json.dumps(env) + "\n")
with open(os.environ["BARE"], "w") as f:
    f.write(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")
PY
export CLAUDE_CODE_ENTRYPOINT=claude-desktop CLAUDE_PLUGIN_DATA="$W/data"
unset CLAUDE_PLUGIN_OPTION_LINK_CHECK

# probe <reply> [stop_hook_active] [transcript]: prints block / pass / crash
probe() {
  python3 - "$1" "${2:-false}" "${3:-$TRANSCRIPT}" <<'PY'
import json, os, subprocess, sys
payload = {"hook_event_name": "Stop", "cwd": os.environ["WORK"], "scratchpad_dir": os.environ["SCRATCH"],
           "transcript_path": sys.argv[3], "stop_hook_active": sys.argv[2] == "true",
           "last_assistant_message": sys.argv[1], "session_id": "s1"}
p = subprocess.run(["python3", os.environ["HOOK"]], input=json.dumps(payload), capture_output=True, text=True)
raw = p.stdout.strip()
if p.returncode != 0 or p.stderr.strip():
    print("crash")
elif not raw:
    print("pass")
else:
    print(json.loads(raw).get("decision") or "other")
PY
}
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }

echo '=== which links fire ==='
row "relative path that does not exist" "$(probe 'See [x](docs/missing.md).')" block
row "relative path that exists" "$(probe 'See [a](docs/a.md).')" pass
row ":42 suffix on an existing file" "$(probe 'See [a](docs/a.md:42).')" pass
row "%20 / %28 / %29 decoded" "$(probe 'See [a](docs/a%20%281%29.md).')" pass
row "URL and in-app anchors ignored" "$(probe 'See [u](https://example.com/x) [s](#local_abc) [t](#terminal/1) [m](mailto:a@example.com).')" pass
row "absolute path outside the session folders" "$(probe "See [r]($OUTSIDE/runbook.md).")" block
row "absolute path in the scratchpad" "$(probe "See [o]($SCRATCH/out.png).")" pass
row "absolute path in an added directory" "$(probe "See [n]($ADDED/notes.md).")" pass
row "relative path escaping the working directory" "$(probe 'See [r](../outside/runbook.md).')" block
row "link inside a code block or inline code" "$(probe $'```\n[x](docs/missing.md)\n```\nand `[y](docs/missing.md)`')" pass
row "placeholder target with no letter or digit" "$(probe 'See [x](…).')" pass

echo '=== when it stays quiet ==='
row "stop_hook_active (already continued once)" "$(probe 'See [x](docs/missing.md).' true)" pass
row "no environment entry: existing outside path passes" "$(probe "See [r]($OUTSIDE/runbook.md)." false "$BARE")" pass
row "no environment entry: missing path still fires" "$(probe 'See [x](docs/missing.md).' false "$BARE")" block
row "malformed input exits 0 silently" "$(out=$(echo 'not json' | python3 "$HOOK" 2>&1); rc=$?; [ "$rc" = 0 ] && [ -z "$out" ] && echo pass || echo crash)" pass
row "not the desktop app" "$(CLAUDE_CODE_ENTRYPOINT=cli probe 'See [x](docs/missing.md).')" pass

echo '=== modes ==='
row "off: no block" "$(CLAUDE_PLUGIN_OPTION_LINK_CHECK=off probe 'See [x](docs/missing.md).')" pass
row "off: nothing written" "$([ -e "$W/data/link-check" ] && echo written || echo none)" none
row "observe: no block" "$(CLAUDE_PLUGIN_OPTION_LINK_CHECK=observe probe 'See [x](docs/missing.md).')" pass
row "observe: one record written" "$(cat "$W"/data/link-check/*.jsonl 2>/dev/null | grep -c 'docs/missing.md')" 1

echo '=== the block reason ==='
reason=$(python3 - <<'PY'
import json, os, subprocess
payload = {"cwd": os.environ["WORK"], "scratchpad_dir": os.environ["SCRATCH"], "transcript_path": os.environ["TRANSCRIPT"],
           "last_assistant_message": "See [x](docs/missing.md:7)."}
print(json.loads(subprocess.run(["python3", os.environ["HOOK"]], input=json.dumps(payload), capture_output=True, text=True).stdout)["reason"])
PY
)
row "names the target without its :line suffix" "$(echo "$reason" | grep -q 'docs/missing.md ' && echo ok || echo missing)" ok

rm -rf "$W"
