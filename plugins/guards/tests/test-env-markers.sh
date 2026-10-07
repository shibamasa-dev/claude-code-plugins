#!/bin/bash
# 通過マーカー（PIP_FREEZE_OK / SHARED_VENV_OK）が、対象コマンド自身の先頭の環境変数代入としてだけ効くこと。
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"
# shared-venv-guard は設定 shared_venv_dirs に書いた置き場にだけ効く（既定は空）
export CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS='~/.venvs'

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

row() { printf '  %-58s -> %-5s (%s 期待)\n' "$2" "$(probe "$1")" "$3"; }

echo '=== pip-freeze-guard ==='
row 'pip freeze > req.txt'                               'マーカー無し'                    'deny'
row 'PIP_FREEZE_OK=1 pip freeze > req.txt'               'pip freeze 自身の先頭にマーカー'   'allow'
row 'echo PIP_FREEZE_OK=1; pip freeze > req.txt'         'マーカーを echo の引数に'          'deny'
row 'pip freeze > req.txt # PIP_FREEZE_OK=1'             'マーカーをコメントに'              'deny'

echo
echo '=== shared-venv-guard ==='
row 'uv pip sync --python ~/.venvs/x req.txt'                         'マーカー無し'                  'deny'
row 'SHARED_VENV_OK=1 uv pip sync --python ~/.venvs/x req.txt'        'uv 自身の先頭にマーカー'         'allow'
row 'echo SHARED_VENV_OK=1; uv pip sync --python ~/.venvs/x req.txt'  'マーカーを echo の引数に'        'deny'
row 'uv pip install --python ~/.venvs/x requests'                     'install（追加のみ）は対象外'     'allow'
row "uv pip sync --python $HOME/.venvs/x req.txt"                     '置き場を絶対パスで指す'          'deny'
row 'uv pip sync --python ~/.venvs-backup/x req.txt'                  '名前が似ているだけの別のフォルダ' 'allow'
row 'uv pip sync --python ~/.venvs req.txt'                            '置き場そのもの'                  'deny'
row 'uv pip sync --python .venv req.txt'                              '置き場の外の venv'               'allow'

echo
echo '=== shared-venv-guard: 設定 shared_venv_dirs が空のとき（既定） ==='
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS= row 'uv pip sync --python ~/.venvs/x req.txt' '設定が空なら効かない'    'allow'
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS='~/shared-envs' row 'uv pip sync --python ~/shared-envs/x req.txt' '別の置き場を設定' 'deny'
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS='~/shared-envs' row 'uv pip sync --python ~/.venvs/x req.txt'       '設定していない置き場'   'allow'
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS= row 'pip freeze > req.txt'                     'pip-freeze-guard は設定に依らない' 'deny'
