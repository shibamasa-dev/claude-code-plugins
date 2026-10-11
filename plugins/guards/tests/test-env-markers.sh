#!/bin/bash
# The bypass marker (PIP_FREEZE_OK) works only as an env var assignment at the start of the target command itself.
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"

probe() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]},
                      "cwd": os.path.expanduser("~")})
p = subprocess.run(["python3", os.environ["HOOK"]], input=payload, capture_output=True, text=True)
out = p.stdout.strip()
if not out:
    print("allow"); raise SystemExit
print(json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision", "allow"))
PY
}

row() { printf '  %-58s -> %-5s (expect %s)\n' "$2" "$(probe "$1")" "$3"; }

echo '=== pip-freeze-guard ==='
row 'pip freeze > req.txt'                               'no marker'                          'deny'
row 'PIP_FREEZE_OK=1 pip freeze > req.txt'               'marker at the start of pip freeze'  'allow'
row 'echo PIP_FREEZE_OK=1; pip freeze > req.txt'         'marker as an echo argument'         'deny'
row 'pip freeze > req.txt # PIP_FREEZE_OK=1'             'marker in a comment'                'deny'

echo
echo '=== shared-venv-guard was removed in 0.5.0 ==='
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS='~/.venvs' row 'uv pip sync --python ~/.venvs/x req.txt' 'not blocked even with the old setting left over' 'allow'
