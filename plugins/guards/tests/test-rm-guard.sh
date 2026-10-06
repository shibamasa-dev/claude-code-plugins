#!/bin/bash
# rm-guard（bash-guard.py の再帰 rm ガード）の実測。
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"
# A〜K は worktree をまとめて置くフォルダを ~/.worktrees に設定した状態で見る（設定 worktree_dirs。
# Claude Code は userConfig の値を CLAUDE_PLUGIN_OPTION_<KEY> でフックに渡す）。設定が空のときは L で見る
export CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/.worktrees'

probe() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]},
                      "cwd": os.environ.get("PROBE_CWD") or os.path.expanduser("~")})
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
row 'W=~/.worktrees/foo; rm -rf $W'                'worktree 配下を代入（存在しない＝判定不能の worktree）' 'deny'

row 'T=/tmp/a; rm -rf $T'                          '/tmp を代入（worktree 以外は変数経由でも allow）' 'allow'

echo
echo '=== C: 解決できない変数は従来どおり deny（安全側） ==='
row 'rm -rf $UNKNOWN_VAR'                          '代入が無い変数'                      'deny'
row 'X=$(pwd); rm -rf $X'                          'コマンド置換の右辺（解決不能）'       'deny'
row 'Y=/tmp/a; rm -rf $Z'                          '別名の変数を参照'                    'deny'
row 'T=/tmp/a; T=$HOME/x; rm -rf $T'               '解決できない値で再代入'              'deny'
row 'echo T=/tmp/a; rm -rf $T'                     '引数の中の T=… は代入ではない'       'deny'
row 'false && T=/tmp/a; rm -rf $T'                 '実行されるとは限らない代入'          'deny'
row 'rm -rf $T; T=/tmp/a'                          '削除より後ろの代入'                  'deny'

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
T0=${TMPDIR:-/tmp}; FH=$(mktemp -d "${T0%/}/wtguard-home.XXXX")   # 末尾の / を落とす（$HOME に // が入ると実環境と違う判定になる）
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

echo
echo '=== I: ラッパー・サブシェル・コマンド置換・find の中の削除も同じ判定 ==='
row 'sudo rm -rf /'                                'sudo 経由'                           'deny'
row 'env rm -rf ~'                                 'env 経由'                            'deny'
row 'command rm -rf ~'                             'command 経由'                        'deny'
row 'nohup rm -rf ~ &'                             'nohup 経由'                          'deny'
row "bash -c 'rm -rf ~'"                           'bash -c の文字列'                    'deny'
row 'sh -c "rm -rf ~"'                             'sh -c の文字列'                      'deny'
row "eval 'rm -rf ~'"                              'eval の文字列'                       'deny'
row 'echo ~ | xargs rm -rf'                        'xargs 経由（引数は標準入力）'         'deny'
row 'find ~ -delete'                               'find -delete'                        'deny'
row 'find ~ -name x -exec rm {} +'                 'find -exec rm'                       'deny'
row '(rm -rf ~)'                                   'サブシェル'                          'deny'
row 'echo $(rm -rf ~)'                             'コマンド置換 $( )'                    'deny'
row 'echo `rm -rf ~`'                              'コマンド置換（バッククォート）'        'deny'
row 'echo "$(rm -rf ~)"'                           'ダブルクォート内のコマンド置換'        'deny'
row 'sudo rm -rf /tmp/x'                           'sudo 経由でも /tmp は allow'          'allow'
row "bash -c 'rm -rf ./build'"                     'bash -c でも相対パスは allow'         'allow'
row "find . -name '*.pyc' -delete"                 'カレントからの find -delete'          'allow'
row 'find /tmp/x -exec rm {} +'                    '/tmp からの find -exec rm'            'allow'
row 'echo "(rm -rf ~)"'                            '引用符内の括弧はデータ'               'allow'
row 'sudo --user root rm -rf /'                    'sudo の値を取る長いオプション'        'deny'
row 'sudo -nu root rm -rf /'                       'sudo の短いオプションの束'            'deny'
row 'env -iu FOO rm -rf ~'                         'env の短いオプションの束'             'deny'
row 'timeout --signal KILL 5 rm -rf ~'             'timeout の値を取る長いオプション'     'deny'
row 'find -delete'                                 '開始パスを省いた find -delete'        'deny'
row 'find . -delete'                               '条件なしでカレントから find -delete'   'deny'
row 'find -L . -mindepth 1 -delete'                '大域オプションだけの find -delete'     'deny'
row "find -name '*.pyc' -delete"                   '開始パス省略でも条件付きなら allow'    'allow'
row 'find /tmp -maxdepth 0 -exec rm -rf ~/data ;'   'find -exec rm の中の別パス'            'deny'
row "find . -name x -exec sh -c 'rm -rf ~' ;"       'find -exec sh -c の中の削除'           'deny'
# 開始パスの中は worktree-guard が走査するので、ホーム（CI では大きい）ではなく小さいフォルダで見る
SMALL=$(mktemp -d "${TMPDIR:-/tmp}/rmguard-small.XXXX")
PROBE_CWD="$SMALL" row "find . -type d -name build -exec rm -rf {} +"  'find -exec rm {} は開始パスの判定'     'allow'
rm -rf "$SMALL"
row "X=/tmp/a; bash -c 'rm -rf \$X/*'"                '子シェルには export していない変数が見えない' 'deny'
row "export X=/tmp/a; bash -c 'rm -rf \$X/x'"         'export しても静的には決めない（安全側）'   'deny'
row 'if false; then T=/tmp/a; fi; rm -rf $T'        'if の中の代入は実行されるとは限らない'     'deny'
row 'T=; rm -rf ${T:-/}'                            '演算子つきの変数展開'                  'deny'
row 'T=/tmp/a; rm -rf ${T}/x'                       '${VAR} の形は従来どおり解決'           'allow'

echo
echo '=== J: worktree の削除マーカーは削除コマンド自身の先頭でだけ効く・相対パスも解決する ==='
# H の続き: sq は未コミットのファイルがあるので未マージ扱い
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'WORKTREE_RM_OK=1 git worktree remove ~/.worktrees/sq' 'マーカーを削除コマンドの先頭に'          'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'WORKTREE_RM_OK=1 trash ~/.worktrees/sq'               'マーカーを trash の先頭に'               'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'echo WORKTREE_RM_OK=1; git worktree remove ~/.worktrees/sq' 'マーカーを echo の引数に'        'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'git worktree remove ~/.worktrees/sq # WORKTREE_RM_OK=1' 'マーカーをコメントに'              'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'WORKTREE_RM_OK=1 true; git worktree remove ~/.worktrees/sq' 'マーカーを別のコマンドの先頭に'   'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'git -C ~/repo worktree remove ~/.worktrees/sq'       'git -C 付きの worktree remove'          'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'cd ~/.worktrees && rm -rf sq'                        'cd してから相対パスで rm -rf'           'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" PROBE_CWD="$FH/.worktrees" row 'rm -rf sq'                'cwd が ~/.worktrees で相対パス rm -rf'  'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'rm -rf ~/.worktrees'                                 '~/.worktrees そのもの'                  'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'sudo trash ~/.worktrees/sq'                          'sudo 経由の trash'                      'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'cd ~/.worktrees/sq && rm -rf build'                  'worktree の中のサブディレクトリ掃除'    'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH" PROBE_CWD="$FH/.worktrees/sq" row 'rm -rf node_modules'  'cwd が worktree の中で相対パス rm -rf'  'allow'
echo
echo '=== K: ~/.worktrees の外にある worktree（<repo>/.claude/worktrees など）も同じ判定 ==='
# feat は main より 1 コミット進んだ未マージ、done は main と同じでクリーン
git -C "$FH/repo" worktree add -q -b feat/cc "$FH/repo/.claude/worktrees/feat"
git -C "$FH/repo/.claude/worktrees/feat" commit -q --allow-empty -m work
git -C "$FH/repo" worktree add -q -b done/cc "$FH/repo/.claude/worktrees/done"
mkdir -p "$FH/repo/.claude/worktrees/feat/build" "$FH/repo/build"
K() { HOME="$FH" PATH="$FH/bin-other:$PATH" PROBE_CWD="${KCWD:-$FH/repo}" row "$@"; }
K 'rm -rf .claude/worktrees/feat'                 '未マージの worktree を相対パスで rm -rf'   'deny'
K "rm -rf $FH/repo/.claude/worktrees/feat"        '未マージの worktree を絶対パスで rm -rf'   'deny'
K 'trash .claude/worktrees/feat'                  '未マージの worktree を trash'             'deny'
K 'find .claude/worktrees/feat -delete'           '未マージの worktree を find -delete'      'deny'
K 'rm -rf .claude/worktrees'                      '未マージの worktree を含むフォルダごと'     'deny'
K 'rm -rf .claude'                                'さらに上のフォルダごと'                    'deny'
K 'WORKTREE_RM_OK=1 rm -rf .claude/worktrees/feat' 'マーカーを削除コマンドの先頭に'           'allow'
K 'rm -rf .claude/worktrees/done'                 'マージ済みでクリーンな worktree'          'allow'
K 'git worktree remove .claude/worktrees/done'    'マージ済みを git worktree remove'        'allow'
K 'rm -rf .claude/worktrees/feat/build'           'worktree の中のサブディレクトリ掃除'      'allow'
KCWD="$FH/repo/.claude/worktrees/feat" K 'rm -rf build' 'cwd が worktree の中で相対パス rm -rf' 'allow'
K 'rm -rf build'                                  'worktree を含まないフォルダ'              'allow'
K 'rm -rf .claude/worktrees/*'                    'glob で未マージの worktree を含む'        'deny'
K 'rm -rf .claude/worktrees/f*'                   'glob の前方一致で未マージの worktree'     'deny'
K 'rm -rf .claude/worktrees/d*'                   'glob がマージ済みの worktree だけに当たる' 'allow'
# git の管理下でないフォルダに worktree をまとめて置いている場合
git -C "$FH/repo" worktree add -q -b feat/ext "$FH/ext/feat"
git -C "$FH/ext/feat" commit -q --allow-empty -m work
K "rm -rf $FH/ext"                                'git 管理外の上位フォルダごと（絶対パス）' 'deny'
KCWD="$FH" K 'rm -rf ext'                         'git 管理外の上位フォルダごと（相対パス）' 'deny'
K 'rm -rf .claude/{worktrees,cache}'              'ブレース展開で未マージの worktree を含む'  'deny'
K 'rm -rf .claude/{cache,tmp}'                    'ブレース展開が worktree に当たらない'      'allow'
K "find . -name '*.pyc' -delete"                  '条件付きの find -delete（掃除）'          'allow'
K 'find . -name feat -exec rm -rf {} +'           '条件付きでも -exec rm は止める側'          'deny'
# 関係ないリポの中に、別のリポの未マージ worktree がある場合
git -C "$FH" init -q -b main outer && git -C "$FH/outer" commit -q --allow-empty -m base
git -C "$FH/repo" worktree add -q -b feat/nested "$FH/outer/bucket/feat"
git -C "$FH/outer/bucket/feat" commit -q --allow-empty -m work
KCWD="$FH/outer" K 'rm -rf bucket'                '別のリポの中にある未マージの worktree'    'deny'
# 深い所にある worktree も拾う（深さで打ち切らない）
git -C "$FH/repo" worktree add -q -b feat/deep "$FH/deep/a/b/c/d/e/feat"
git -C "$FH/deep/a/b/c/d/e/feat" commit -q --allow-empty -m work
K "rm -rf $FH/deep"                               '6 段下にある未マージの worktree'          'deny'
# 見るフォルダの数の上限で打ち切ったら、見ていない所に worktree が無いとは言えないので止める
# （一時領域が /tmp でない macOS でも rm-guard に止められないよう、相対パスで見る）
mkdir -p "$FH/wide/1" "$FH/wide/2" "$FH/wide/3" "$FH/wide/4"
KCWD="$FH" GUARDS_SCAN_LIMIT=3 K 'rm -rf wide'    '走査が上限で打ち切られた（判定不能）'      'deny'
KCWD="$FH" K 'rm -rf wide'                        '上限内で worktree が無いと確かめられた'    'allow'
KCWD="$FH" GUARDS_SCAN_LIMIT=3 K "find wide -name x -exec rm -rf {} +" '条件付きの find -exec rm でも走査しきれなければ止める' 'deny'
K 'rm -rf .claude/worktrees/x{1..1000000000}'      '巨大な範囲でも固まらずに判定不能で止める'  'deny'
# 範囲のブレース展開・展開の数の上限・引用符で囲んだ glob の文字
K 'rm -rf .claude/worktrees/{done,fea{s..u}}'      '範囲のブレース展開で未マージの worktree'   'deny'
K "rm -rf .claude/{$(printf 'x%s,' $(seq 1 300))worktrees}" 'ブレース展開が上限を超えた（判定不能）' 'deny'
mkdir -p "$FH/repo/bk"
git -C "$FH/repo" worktree add -q -b feat/bk "$FH/repo/bk/b[1]"
git -C "$FH/repo/bk/b[1]" commit -q --allow-empty -m work
K "rm -rf 'bk/b[1]'"                               '引用符で囲んだ [ ] は文字どおりのパス'     'deny'
git -C "$FH/repo" worktree add -q -b feat/bk2 "$FH/repo/bk/{done,feat}"
git -C "$FH/repo/bk/{done,feat}" commit -q --allow-empty -m work
K "rm -rf 'bk/{done,feat}'"                        '引用符で囲んだ { } は文字どおりのパス'     'deny'
# $TMPDIR の下の worktree（rm-guard は $TMPDIR を安全扱いにする）
git -C "$FH/repo" worktree add -q -b feat/tmp "$FH/tmpd/feat"
git -C "$FH/repo/../tmpd/feat" commit -q --allow-empty -m work
TMPDIR="$FH/tmpd" K 'rm -rf "$TMPDIR/feat"'        '$TMPDIR の下の未マージの worktree'         'deny'
TMPDIR="$FH/tmpd" K 'rm -rf ${TMPDIR:-/tmp}/feat'  '${TMPDIR:-…} の形でも'                    'deny'
TMPDIR="$FH/tmpd" K 'rm -rf "$TMPDIR/other"'       '$TMPDIR の下の worktree でないパス'        'allow'
# フックが別の worktree の GIT_DIR を受け継いでいても、消す先のリポで判定する
GIT_DIR="$FH/repo/.git/worktrees/done" GIT_WORK_TREE="$FH/repo/.claude/worktrees/done" \
  K 'rm -rf .claude/worktrees/feat'               'GIT_DIR が別の worktree を指していても'    'deny'

echo
echo '=== L: 設定 worktree_dirs（空＝既定・値あり）で、どのガードが止めるか ==='
# 一時領域（/tmp）は rm-guard が通すので、ここでは存在しない HOME（一時領域の外）で見る。
# 出力は allow / wtguard（worktree-guard が止めた）/ rmguard（rm-guard が止めた）
who() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}, "cwd": "/"})
out = subprocess.run(["python3", os.environ["HOOK"]], input=payload, capture_output=True, text=True).stdout.strip()
if not out:
    print("allow"); raise SystemExit
r = json.loads(out).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
print("wtguard" if "worktree-guard" in r else "rmguard" if "rm-guard" in r else "other")
PY
}
lrow() { printf '  %-58s -> %-7s (%s 期待)\n' "$2" "$(who "$1")" "$3"; }
NH=/nonexistent-guards-home
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS= HOME=$NH lrow 'rm -rf ~/.worktrees/x'      '空: ~/.worktrees は特別扱いしない'          'rmguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS= HOME=$NH lrow 'W=~/.worktrees/x; rm -rf $W' '空: 変数経由でも同じ'                        'rmguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/.worktrees' HOME=$NH lrow 'rm -rf ~/.worktrees/x' '~/.worktrees: 判定できない worktree として止める' 'wtguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/wt, ~/.worktrees' HOME=$NH lrow 'rm -rf ~/wt/x'       'カンマ区切りの1つ目'      'wtguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/wt, ~/.worktrees' HOME=$NH lrow 'rm -rf ~/.worktrees/x' 'カンマ区切りの2つ目'    'wtguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='/' HOME=$NH lrow 'rm -rf /opt/x'               'ルートは置き場として受け付けない'            'rmguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~' HOME=$NH lrow 'rm -rf ~/x'                  'ホームも置き場として受け付けない'            'rmguard'

echo
echo '=== M: rm-guard はマージ済みでクリーンな worktree の root を置き場に関係なく通す ==='
# 一時領域の扱いを外して rm-guard の分類だけを見る（K の feat は未マージ、done はマージ済みでクリーン）
classify() {
  CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS= HOME="$FH" PATH="$FH/bin-other:$PATH" python3 - "$1" <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("bash_guard", os.environ["HOOK"])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.SAFE_PREFIXES = ()
print(m._classify_target(sys.argv[1]))
PY
}
crow() { printf '  %-58s -> %-5s (%s 期待)\n' "$2" "$(classify "$1")" "$3"; }
crow "$FH/repo/.claude/worktrees/done"            'マージ済みでクリーンな worktree の root'   'safe'
crow "$FH/repo/.claude/worktrees/feat"            '未マージの worktree の root'               'other'
crow "$FH/repo/.claude/worktrees/done/build"      'worktree の root でないパス'               'other'
crow "$FH/repo"                                   'メインの作業ツリー'                        'other'

rm -rf "$FH"
