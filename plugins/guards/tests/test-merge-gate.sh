#!/bin/bash
# merge-gate（bash-guard.py ルール1）の実測。マージ対象のリポをコマンド自身から決めているか。
# 使い捨てのリポを一時ディレクトリに作り、gh は偽物にする（ネットワークに出ない）。
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"

W=$(mktemp -d "${TMPDIR:-/tmp}/mergegate.XXXX")
mkrepo() {  # mkrepo <dir> [origin-url]
  git init -q -b main "$1" && git -C "$1" commit -q --allow-empty -m base
  [ -n "${2:-}" ] && git -C "$1" remote add origin "$2"
  return 0
}
mkrepo "$W/noremote"
mkrepo "$W/allowed" https://github.com/allowed/repo.git
mkrepo "$W/victim"  https://github.com/victim/repo.git
git -C "$W/victim" update-ref refs/remotes/origin/main HEAD   # upstream 追いつきの確認用
mkdir -p "$W/bin"
# 偽 gh: `gh pr list` だけに答える。-R があればそのリポ、無ければ cwd の origin で決める。
# empty/repo だけオープン PR 0 件、それ以外は 1 件。
cat > "$W/bin/gh" <<'EOF'
#!/bin/bash
[ "$1 $2" = "pr list" ] || exit 1
repo=""
while [ $# -gt 0 ]; do
  case "$1" in -R|--repo) repo=$2; shift ;; esac
  shift
done
[ -z "$repo" ] && repo=$(git remote get-url origin 2>/dev/null | sed -E 's#.*[:/]([^/]+/[^/]+)\.git$#\1#')
[ "$repo" = "empty/repo" ] && echo '[]' || echo '[{"number":1}]'
EOF
chmod +x "$W/bin/gh"
export PATH="$W/bin:$PATH" CLAUDE_PLUGIN_OPTION_MERGE_ALLOWED_REPOS=allowed/repo
export NOREMOTE="$W/noremote" ALLOWED="$W/allowed" VICTIM="$W/victim"

probe() {  # probe <command> <cwd> [permission_mode]
  python3 - "$1" "$2" "${3:-default}" <<'PY'
import json, subprocess, sys, os
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]},
                      "cwd": sys.argv[2], "permission_mode": sys.argv[3]})
p = subprocess.run(["python3", os.environ["HOOK"]], input=payload, capture_output=True, text=True)
out = p.stdout.strip()
if not out:
    print("allow"); raise SystemExit
print(json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision", "allow"))
PY
}

# row <command> <cwd> <label> <expected> [permission_mode]
row() { printf '  %-58s -> %-5s (%s 期待)\n' "$3" "$(probe "$1" "$2" "${5:-default}")" "$4"; }

echo '=== A: 別セグメントのおとりで判定対象のリポをすり替えられないこと ==='
row "git -C $NOREMOTE status; gh pr merge 1 -R victim/repo" "$VICTIM"  'remote 無しリポの git -C をおとりに -R 指定マージ' 'ask'
row "git -C $NOREMOTE status; git merge feature"            "$VICTIM"  'remote 無しリポの git -C をおとりに git merge'     'ask'
row "cd $NOREMOTE && cd - && gh pr merge 1"                  "$VICTIM"  'cd して cd - で戻ってからマージ'                  'ask'
row "git -C $ALLOWED status; gh pr merge 1 -R victim/repo"   "$VICTIM"  '許可リポの git -C をおとりに -R 指定マージ'       'ask'
row "false && cd $NOREMOTE; gh pr merge 1"                   "$VICTIM"  '実行されない条件付き cd をおとりにマージ'        'ask'
row "cd() { :; }; cd $NOREMOTE; gh pr merge 1"                 "$VICTIM"  'cd を関数で無効化してからおとりの cd'          'ask'
row "function cd { :; }; cd $NOREMOTE; git merge feature"        "$VICTIM"  'function 構文で cd を無効化'                    'ask'
row "if false; then cd $NOREMOTE; fi; git merge feature"      "$VICTIM"  'if の中の cd をおとりにマージ'                  'ask'
row "while false; do cd $NOREMOTE; done; gh pr merge 1"       "$VICTIM"  'while の中の cd をおとりにマージ'               'ask'
row "for d in x; do cd $NOREMOTE; done; git merge feature"    "$VICTIM"  'for の中の cd をおとりにマージ'                 'ask'
row "(cd $NOREMOTE); git merge feature"                     "$VICTIM"  'サブシェル内の cd（cd 追跡の退行防止）'              'ask'

echo
echo '=== B: gh のリポ指定（-R / --repo / GH_REPO / PR の URL）を判定に使うこと ==='
row "gh pr merge 1 -R victim/repo"                             "$ALLOWED" '許可リポの cwd から -R で別リポをマージ'          'ask'
row "gh pr merge 1 --repo=victim/repo"                         "$ALLOWED" '許可リポの cwd から --repo= で別リポをマージ'     'ask'
row "gh pr -R victim/repo merge 1"                             "$ALLOWED" 'pr と merge の間に -R を挟む'                    'ask'
row "GH_REPO=victim/repo gh pr merge 1"                        "$ALLOWED" '許可リポの cwd から GH_REPO で別リポをマージ'     'ask'
row "gh pr merge https://github.com/victim/repo/pull/1"        "$ALLOWED" '許可リポの cwd から PR の URL で別リポをマージ'   'ask'
row "export GH_REPO=victim/repo; gh pr merge 1"                "$ALLOWED" '前のセグメントで export した GH_REPO'             'ask'
row "GH_REPO=victim/repo; gh pr merge 1"                       "$ALLOWED" '前のセグメントで代入した GH_REPO'                 'ask'
row "export GH_REPO=allowed/repo; gh pr merge 1"               "$VICTIM"  'export が許可リポでも cwd が別リポ'               'ask'
row "export GH_REPO=allowed/repo; gh pr merge 1"               "$ALLOWED" 'export と cwd がどちらも許可リポ'                 'allow'
GH_REPO=victim/repo row "gh pr merge 1"                        "$ALLOWED" '継承した GH_REPO'                                 'ask'
row "export GIT_DIR=$VICTIM/.git; git merge feature"         "$ALLOWED" '前のセグメントで export した GIT_DIR'             'ask'
row "gh pr merge 1 -R victim/repo"                             "$ALLOWED" 'bypassPermissions では deny'                    'deny' bypassPermissions

echo
echo '=== C: ラッパーの中のマージも見ること ==='
row "bash -c 'gh pr merge 1'"                                  "$VICTIM"  'bash -c の中のマージ'                           'ask'
row "sudo git merge feature"                                   "$VICTIM"  'sudo 経由の git merge'                          'ask'

echo
echo '=== D: 従来どおりの例外は通る（退行なし） ==='
row "gh pr merge 1"                                            "$ALLOWED" '許可リポで自分の cwd からマージ'                'allow'
row "cd $ALLOWED && gh pr merge 1"                           "$NOREMOTE" '先頭の cd で許可リポへ移ってマージ'            'allow'
row "gh pr merge 1 -R allowed/repo"                            "$VICTIM"  '-R で許可リポを指定'                            'allow'
row "gh pr merge 1 -R empty/repo"                              "$VICTIM"  '-R で指定したリポのオープン PR が 0 件'          'allow'
row "git -C $NOREMOTE merge feature"                         "$VICTIM"  'git 自身の -C が remote 無しリポ'                'allow'
row "git merge origin/main"                                    "$VICTIM"  'upstream 追いつきマージ'                        'allow'
row "git merge feature"                                        "$VICTIM"  'オープン PR のあるリポで素の git merge'         'ask'
row "echo 'gh pr merge 1'"                                     "$VICTIM"  '文字列の中のマージ'                             'allow'

rm -rf "$W"
