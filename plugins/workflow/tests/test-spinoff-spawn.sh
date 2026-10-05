#!/bin/bash
# spinoff-session の spawn.sh / nudge.sh の回帰。tmux と claude はスタブに置き換え、渡された引数を記録して確かめる。
set -u
D="$(cd "$(dirname "$0")/.." && pwd)/skills/spinoff-session/scripts"
W=$(mktemp -d "${TMPDIR:-/tmp}/spinoff-test.XXXX")
mkdir -p "$W/bin" "$W/wt"
REPO="$W/repo"; git init -q -b main "$REPO" && git -C "$REPO" -c user.name=test -c user.email=test@example.com commit -q --allow-empty -m init

# tmux スタブ: 呼ばれた引数を1行ずつ記録する。has-session は spin_alive だけ成功させる
cat > "$W/bin/tmux" <<EOF
#!/bin/bash
printf '%s\n' "\$*" >> "$W/tmux.log"
[ "\$1" = has-session ] && [ "\$3" != =spin_alive ] && exit 1
# new-session は渡されたコマンドを実際にシェルで走らせる（claude もスタブなので何もしない）
[ "\$1" = new-session ] && bash -c "\${@: -1}"
exit 0
EOF
chmod +x "$W/bin/tmux"
printf '#!/bin/bash\nexit 0\n' > "$W/bin/claude"; chmod +x "$W/bin/claude"
NO_TMUX="$W/notmux"; mkdir -p "$NO_TMUX"
for c in bash git date head tr sed basename dirname mktemp cat; do ln -sf "$(command -v $c)" "$NO_TMUX/$c"; done

row() { printf '  %-52s -> %-5s (%s 期待)\n' "$1" "$2" "$3"; }
spawn() { PATH="$W/bin:$PATH" SPINOFF_WORKTREE_ROOT="$W/wt" bash "$D/spawn.sh" "$@" >"$W/out" 2>&1; }

echo '=== tmux が無い（Windows など） ==='
PATH="$NO_TMUX" bash "$D/spawn.sh" --no-worktree "$REPO" "x" >"$W/out" 2>&1 && r=run || r=stop
grep -q 'Windows は非対応' "$W/out" || r="$r-nomsg"
row '起動前に止まり、非対応と伝える' "$r" stop

echo '=== 起動（worktree・待機モード） ==='
: > "$W/tmux.log"
spawn "$REPO" "fix the bug" && r=ok || r=fail
row 'spawn.sh が成功する' "$r" ok
ls "$W/wt" | grep -q '^repo-fix-the-bug-' && r=yes || r=no
row 'worktree が作られる' "$r" yes
grep -q 'new-session -d -s spin_fix-the-bug-' "$W/tmux.log" && r=yes || r=no
row 'spin_ 接頭辞の tmux セッションで起動する' "$r" yes
grep -q '待機タスク' "$W/tmux.log" && r=yes || r=no
row '既定は待機モード' "$r" yes
grep -q -- '--model' "$W/tmux.log" && r=yes || r=no
row '--model を省くとモデルを指定しない' "$r" no
PATH="$W/bin:$PATH" SPINOFF_WORKTREE_ROOT="$W/wt" bash "$D/list.sh" 2>/dev/null | grep -q "$W/wt/repo-fix-the-bug-" && r=yes || r=no
row 'list.sh が SPINOFF_WORKTREE_ROOT の worktree を出す' "$r" yes

echo '=== 差し込み口 ==='
: > "$W/tmux.log"
SPINOFF_SEED_APPENDIX_CMD='echo "APPENDIX for $SPINOFF_SESSION"' \
SPINOFF_POST_SPAWN_CMD="echo \"\$SPINOFF_SESSION \$SPINOFF_ISSUE\" > $W/post.txt" \
  spawn --no-worktree --issue example/repo#7 "$REPO" "task" && r=ok || r=fail
row '--issue 付きで起動できる' "$r" ok
grep -q 'APPENDIX for spin_issue-7-' "$W/tmux.log" && r=yes || r=no
row 'SPINOFF_SEED_APPENDIX_CMD の出力がタスク文に足される' "$r" yes
grep -q '^spin_issue-7-.* example/repo#7$' "$W/post.txt" 2>/dev/null && r=yes || r=no
row 'SPINOFF_POST_SPAWN_CMD にセッション名と issue が渡る' "$r" yes
grep -q '待機タスク' "$W/tmux.log" && r=yes || r=no
row '--issue の既定は投げっぱなし' "$r" no
SPINOFF_SEED_APPENDIX_CMD='exit 1' spawn --no-worktree "$REPO" "task" && r=ok || r=fail
row '差し込み口が失敗しても起動は続ける' "$r" ok

echo '=== nudge.sh ==='
: > "$W/tmux.log"
PATH="$W/bin:$PATH" bash "$D/nudge.sh" spin_alive "review please" >/dev/null 2>&1 && r=ok || r=fail
row '稼働中の spin_ に送れる' "$r" ok
grep -q -- '-l review please' "$W/tmux.log" && r=yes || r=no
row 'メッセージは文字どおり送る（-l）' "$r" yes
PATH="$W/bin:$PATH" bash "$D/nudge.sh" other "x" >/dev/null 2>&1 && r=ok || r=refuse
row 'spin_ 以外のセッションには送らない' "$r" refuse
PATH="$W/bin:$PATH" bash "$D/nudge.sh" spin_gone "x" >/dev/null 2>&1 && r=ok || r=refuse
row '存在しないセッションには送らない' "$r" refuse
grep -q -- '-t =spin_alive' "$W/tmux.log" && r=yes || r=no
row 'セッション名は完全一致で指定する（=）' "$r" yes

echo '=== --model の値はシェルに解釈させない ==='
: > "$W/tmux.log"
spawn --no-worktree --model '$(touch '"$W"'/pwned)' "$REPO" "task" >/dev/null 2>&1
[ -e "$W/pwned" ] && r=yes || r=no
row 'モデル名に書いたコマンドは実行されない' "$r" no

echo '=== list-projects.sh ==='
git -C "$REPO" worktree add -q "$W/proj/linked" -b linked main 2>/dev/null
mkdir -p "$W/proj"; cp -R "$REPO" "$W/proj/clone"; mkdir -p "$W/proj/fake/.git"
out=$(bash "$D/list-projects.sh" "$W/proj")
echo "$out" | grep -q "$W/proj/linked" && r=yes || r=no
row 'linked worktree（.git がファイル）も出す' "$r" yes
echo "$out" | grep -q "$W/proj/clone" && r=yes || r=no
row '通常の clone を出す' "$r" yes
echo "$out" | grep -q "$W/proj/fake" && r=yes || r=no
row 'git でない .git ディレクトリは出さない' "$r" no

git -C "$REPO" worktree prune 2>/dev/null
rm -rf "$W"
