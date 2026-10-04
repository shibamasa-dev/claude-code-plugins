#!/bin/bash
# rm-guard（bash-guard.py の再帰 rm ガード）の実測。
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"

probe() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]},
                      "cwd": os.path.expanduser("~")})
p = subprocess.run(["python3", os.environ["HOOK"]],
                   input=payload, capture_output=True, text=True)
out = p.stdout.strip()
if not out:
    print("allow"); raise SystemExit
print(json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision", "allow"))
PY
}

row() { printf '  %-58s -> %-5s (%s 期待)\n' "$2" "$(probe "$1")" "$3"; }

echo '=== A: マーカーが効かなくなったこと ==='
row "RM_GUARD_OK=1 rm -rf $HOME/somewhere" 'RM_GUARD_OK=1 付き（絶対パス）'    'deny'
row 'RM_GUARD_OK=1 rm -rf /'                       'RM_GUARD_OK=1 付き（ルート）'       'deny'
row "SKIP=1 FORCE=1 rm -rf $HOME/somewhere" '別名の環境変数付き'                'deny'

echo
echo '=== B: 同一コマンド内の変数代入が解決されること（今日踏んだ誤爆） ==='
row 'T=/tmp/tclint-test; rm -rf $T; mkdir -p $T/x' '同一コマンド内で /tmp を代入（今日の実例）' 'allow'
row 'D=/tmp/a; rm -rf ${D}/sub'                    '${VAR}/sub の形'                     'allow'
row 'W=~/.worktrees/foo; rm -rf $W'                'worktree 配下を代入'                 'allow'

echo
echo '=== C: 解決できない変数は従来どおり deny（安全側） ==='
row 'rm -rf $UNKNOWN_VAR'                          '代入が無い変数'                      'deny'
row 'X=$(pwd); rm -rf $X'                          'コマンド置換の右辺（解決不能）'       'deny'
row 'Y=/tmp/a; rm -rf $Z'                          '別名の変数を参照'                    'deny'

echo
echo '=== D: 壊滅的ターゲットは無条件 deny（退行なし） ==='
row 'H=/; rm -rf $H'                               'ルートを変数経由で'                  'deny'
row 'rm -rf ~'                                     'ホーム'                              'deny'
row 'rm -rf /usr'                                  'システムdir'                         'deny'
row 'rm -rf *'                                     '裸のグロブ'                          'deny'

echo
echo '=== E: 従来どおり allow（退行なし） ==='
row 'rm -rf ./build'                               '相対パス'                            'allow'
row 'rm -rf /tmp/foo'                              'リテラルの /tmp'                     'allow'
row "rm -f $HOME/x"                              '再帰でない rm'                       'allow'
row "ls -la $HOME"                               'rm ですらない'                       'allow'

echo
echo '=== F: trash（ゴミ箱移動）は取り消せるので安全領域外でも通す==='
row "trash $HOME/.claude/state/example-tool"   '安全領域外を trash'                  'allow'
row 'trash ~/Documents/old.txt'                    'ホーム配下のファイルを trash'        'allow'
row 'trash ~'                                      'ホームそのもの'                      'deny'
row 'trash /usr'                                   'システムdir'                         'deny'
row 'trash *'                                      '裸のグロブ'                          'deny'
row 'trash ~/.worktrees/no-such-wt'                 '判定不能の worktree を trash'        'deny'

echo
echo '=== G: heredoc の本文・引用符の中はデータ（コマンドとして評価しない） ==='
row $'cat > /tmp/x.md <<\'EOF\'\nrm -rf ~/.claude/state/foo\nEOF' 'heredoc 本文に削除コマンドの文字列'   'allow'
row $'gh issue create --body "手順:\nrm -rf ~/.claude/state/foo"' '引用符内に削除コマンドの文字列'   'allow'
row $'cat > /tmp/x.md <<EOF\nok\nEOF\nrm -rf ~/.claude/state/foo' 'heredoc の後ろにある本物の削除'   'deny'

echo
echo '=== H: squash マージ済みの worktree（main とは別 SHA）は PR の head 一致で消せる ==='
# HOME を一時ディレクトリへ向け、~/.worktrees 配下にブランチが main より 1 コミット進んだ worktree を作る。
# gh は偽物にして「この head の MERGED PR がある／無い」を切り替える（ネットワークに出ない）
FH=$(mktemp -d "${TMPDIR:-/tmp}/wtguard-home.XXXX")
git -C "$FH" init -q -b main repo && git -C "$FH/repo" commit -q --allow-empty -m base
git -C "$FH/repo" worktree add -q -b feat/sq "$FH/.worktrees/sq"
git -C "$FH/.worktrees/sq" commit -q --allow-empty -m work
SQ_HEAD=$(git -C "$FH/.worktrees/sq" rev-parse HEAD)
mkdir -p "$FH/bin-merged" "$FH/bin-other"
printf '#!/bin/bash\necho %s\n' "$SQ_HEAD" > "$FH/bin-merged/gh"
printf '#!/bin/bash\necho 0000000000000000000000000000000000000000\n' > "$FH/bin-other/gh"
chmod +x "$FH/bin-merged/gh" "$FH/bin-other/gh"
HOME="$FH" PATH="$FH/bin-merged:$PATH" row 'git worktree remove ~/.worktrees/sq' 'MERGED PR の head が HEAD と一致'      'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH"  row 'git worktree remove ~/.worktrees/sq' 'MERGED PR の head が別（追加コミットあり）' 'deny'
: > "$FH/.worktrees/sq/dirty.txt"
HOME="$FH" PATH="$FH/bin-merged:$PATH" row 'git worktree remove ~/.worktrees/sq' 'head 一致でも未コミットのファイルがある'  'deny'
