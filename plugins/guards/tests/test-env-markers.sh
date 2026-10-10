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
                      "cwd": os.path.expanduser(os.environ.get("PROBE_CWD") or "~")})
env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
if os.environ.get("PROBE_VIRTUAL_ENV"):
    env["VIRTUAL_ENV"] = os.path.expanduser(os.environ["PROBE_VIRTUAL_ENV"])
p = subprocess.run(["python3", os.environ["HOOK"]], input=payload, capture_output=True, text=True, env=env)
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
row 'uv pip sync --python ~/.venvs>log req.txt'                        '置き場の直後にリダイレクト'      'deny'
row 'uv pip sync --python .venv req.txt'                              '置き場の外の venv'               'allow'
row 'source ~/.venvs/x/bin/activate && uv pip sync req.txt'           'activate で共有 venv に入ってから' 'deny'
row 'cd ~/.venvs/x && uv pip sync req.txt'                            'cd で共有 venv に入ってから'     'deny'
row 'export VIRTUAL_ENV=~/.venvs/x; uv pip sync req.txt'              'export で共有 venv を指してから' 'deny'
row 'VIRTUAL_ENV=~/.venvs/x uv pip sync req.txt'                      '同じコマンドの環境変数で指す'    'deny'
row 'ls ~/.venvs && uv pip sync --python .venv req.txt'               '別のコマンドが言及しているだけ'  'allow'
row 'cd ~/.venvs/x && cd /tmp && uv pip sync req.txt'                 'cd で共有 venv を出た後'         'allow'
row 'cd ~/.venvs/x && uv pip sync --python /tmp/.venv/bin/python r'  '--python で共有 venv の外を明示' 'allow'
row 'source ~/.venvs/x/bin/activate && deactivate && uv pip sync r'  'deactivate した後'               'allow'
row 'source ~/.venvs/x/bin/activate && cd /tmp && uv pip sync r'     'activate 中は cd しても対象'      'deny'
row 'uv pip sync --python /tmp/.venv/bin/python ~/.venvs/req.txt'   '共有 venv は入力ファイルだけ'     'allow'
row 'cd ~/.venvs/x && cd project && uv pip sync req.txt'             '共有 venv の中で相対パスの cd'    'deny'
row 'source ~/.venvs/x/bin/activate && source /tmp/s.sh && uv pip sync r' 'activate 後に別のスクリプト' 'deny'
row 'source ~/.venvs/x/bin/activate && source /p/.venv/bin/activate && uv pip sync r' '別の venv を activate' 'allow'
PROBE_VIRTUAL_ENV='~/.venvs/team' row 'uv pip sync req.txt'                  '引き継いだ VIRTUAL_ENV が共有 venv' 'deny'
PROBE_VIRTUAL_ENV='~/.venvs/team' row 'deactivate && uv pip sync req.txt'    '引き継いだ venv を deactivate'    'allow'
PROBE_CWD='~/.venvs/x' row 'uv pip sync req.txt'                               'フックの cwd が共有 venv の中'     'deny'
row 'cd .venvs/x && uv pip sync req.txt'                                       '相対パスの cd で共有 venv に入る' 'deny'
row 'cd .venvs/x && cd ../.. && uv pip sync req.txt'                           '相対パスの cd で出る'             'allow'
row 'cd -P .venvs/x && uv pip sync req.txt'                                    'cd のオプションの後の相対パス'   'deny'
CDPATH="$HOME/.venvs" row 'cd x && uv pip sync req.txt'                        'CDPATH があるときの相対名の cd'   'deny'
CDPATH="$HOME/.venvs" row 'cd .x && uv pip sync req.txt'                       'CDPATH があるときのドットで始まる名前' 'deny'
CDPATH="$HOME/.venvs" row 'cd ./x && uv pip sync req.txt'                       'CDPATH があっても ./ は今いる場所の下' 'allow'
row 'CDPATH=/srv; cd x && uv pip sync req.txt'                                'コマンドの中で CDPATH を代入'      'deny'
row 'export CDPATH=/srv && cd x && uv pip sync req.txt'                        'コマンドの中で CDPATH を export'   'deny'
row 'CDPATH= cd x && uv pip sync req.txt'                                      '空の CDPATH は効かない'           'allow'
row 'cd ~/.venvs/x && source bin/activate && cd /tmp && uv pip sync r'         '相対パスで共有 venv を activate'  'deny'
row 'cd /tmp/p && source .venv/bin/activate && uv pip sync r'                  '相対パスで別の venv を activate'  'allow'
row 'source "$V/bin/activate" && uv pip sync r'                                '行き先が分からない activate'      'deny'
row 'cd "$WORKDIR" && uv pip sync req.txt'                                     '行き先が分からない cd'            'deny'
row 'pushd ~/.venvs/x && popd && uv pip sync req.txt'                          'pushd で入って popd で戻る'       'allow'
row 'cd ~/.venvs/x && pushd -n /tmp && uv pip sync req.txt'                   'pushd -n は移動しない'            'deny'
row 'pushd -n ~/.venvs/x && popd && uv pip sync req.txt'                       'pushd -n で積んだ先へ popd'       'deny'
row 'pushd -n x && cd ~/.venvs && popd && uv pip sync req.txt'                'pushd -n の相対パスは popd の時点で解く' 'deny'
row 'pushd -n /tmp && popd && uv pip sync req.txt'                              'pushd -n の絶対パスへ popd'       'allow'
row 'pushd ~/.venvs/x && pushd /tmp && pushd && uv pip sync req.txt'            '引数なしの pushd で入れ替え'      'deny'
row 'cd ~/.venvs/x && pushd /tmp && pushd && pushd && uv pip sync req.txt'      '引数なしの pushd を2回で戻る'     'allow'
row 'pushd ~/.venvs/x && pushd /tmp && popd -n && uv pip sync req.txt'          'popd -n は移動しない'             'allow'
row 'pushd /tmp && pushd +1 && uv pip sync req.txt'                             'スタックの番号で移動'             'deny'

echo
echo '=== shared-venv-guard: 設定 shared_venv_dirs が空のとき（既定） ==='
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS= row 'uv pip sync --python ~/.venvs/x req.txt' '設定が空なら効かない'    'allow'
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS='~/shared-envs' row 'uv pip sync --python ~/shared-envs/x req.txt' '別の置き場を設定' 'deny'
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS='~/shared-envs' row 'uv pip sync --python ~/.venvs/x req.txt'       '設定していない置き場'   'allow'
CLAUDE_PLUGIN_OPTION_SHARED_VENV_DIRS= row 'pip freeze > req.txt'                     'pip-freeze-guard は設定に依らない' 'deny'
