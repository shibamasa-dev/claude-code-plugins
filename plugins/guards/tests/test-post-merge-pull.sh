#!/bin/bash
# git-freshness.py の post-merge-pull の実測。マージの後に、手元のマージ先ブランチを追従させるか。
# GitHub コネクタのマージ（mcp__*__merge_pull_request）は、cwd の origin が同じリポのときだけ動くか。
# origin の URL は github.com の形にし、insteadOf で手元の bare リポへ向ける（ネットワークに出ない）。
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/git-freshness.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/pmp.XXXX")
export HOME="$T" GIT_CONFIG_NOSYSTEM=1
git config --global user.email t@example.com; git config --global user.name t
git config --global init.defaultBranch main
git config --global advice.detachedHead false
git config --global url."file://$T/origin.git".insteadOf https://github.com/O/R.git
# gh は偽物にする（本物の gh が GitHub に問い合わせないように）。既定は失敗＝マージ先が取れない
mkdir -p "$T/bin"; printf '#!/bin/sh\nexit 1\n' > "$T/bin/gh"; chmod +x "$T/bin/gh"; export PATH="$T/bin:$PATH"
git init -q --bare "$T/origin.git"
git clone -q https://github.com/O/R.git "$T/up" 2>/dev/null
( cd "$T/up" && git commit -q --allow-empty -m init && git push -q origin main )
git clone -q https://github.com/O/R.git "$T/me" 2>/dev/null
advance() { ( cd "$T/up" && git commit -q --allow-empty -m "c$RANDOM" && git push -q origin main ); }
behind() { git -C "$T/me" fetch -q origin main; git -C "$T/me" rev-list --count HEAD..origin/main; }

# run <tool_name> <tool_input(JSON)> [tool_response(JSON)]
run() {
  printf '{"hook_event_name":"PostToolUse","session_id":"s","cwd":"%s","tool_name":"%s","tool_input":%s,"tool_response":%s}' \
    "$T/me" "$1" "$2" "${3:-\"ok\"}" | python3 "$HOOK"
}
# コネクタの結果の形（[{"type":"text","text":"{\"sha\":...}"}]）
merged() { python3 -c 'import json,sys; print(json.dumps([{"type":"text","text":json.dumps({"sha":sys.argv[1],"merged":True})}]))' "$1"; }
res() { case "$1" in *⚠️*) echo warned ;; *自動\ pull*) echo pulled ;; '') echo silent ;; *) echo other ;; esac; }
row() { printf '  %-58s -> %-7s (%s 期待)\n' "$1" "$2" "$3"; }

advance
row 'gh pr merge の後、main が遅れていれば pull する' "$(res "$(run Bash '{"command":"gh pr merge 3 --squash"}')")" pulled
row '追従済みなら何も言わない' "$(res "$(run Bash '{"command":"gh pr merge 3 --squash"}')")" silent
advance
row 'コネクタのマージ（同じリポ・owner の大小は無視）' "$(res "$(run mcp__github__merge_pull_request '{"owner":"o","repo":"r","pullNumber":3}')")" pulled
advance
row 'コネクタのマージ（別のリポ）は手元を動かさない' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"other","pullNumber":3}')")" silent
row '  そのとき main は遅れたまま' "$( [ "$(behind)" -gt 0 ] && echo behind || echo synced)" behind
row 'マージ以外のコネクタのツールは見ない' "$(res "$(run mcp__github__pull_request_read '{"owner":"O","repo":"R","pullNumber":3}')")" silent
( cd "$T/up" && echo a > README && git add README && git commit -q -m readme && git push -q origin main )
git -C "$T/me" pull -q --ff-only origin main
echo local > "$T/me/README"   # 手元の未コミット変更
( cd "$T/up" && echo b > README && git commit -q -am readme2 && git push -q origin main )
row 'ff できないローカルの変更があれば触らず知らせる' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":4}')")" warned
git -C "$T/me" checkout -q -b feat
row 'マージ先（main）以外のブランチでは動かない' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":4}')")" silent

# マージ先が develop の PR（既定ブランチの main とは別）
git -C "$T/me" checkout -q -f main && git -C "$T/me" checkout -q -- . 2>/dev/null
( cd "$T/up" && git pull -q origin main && git checkout -q -b develop && git commit -q --allow-empty -m d0 && git push -q origin develop )
git -C "$T/me" fetch -q origin && git -C "$T/me" checkout -q -b develop origin/develop
adv_dev() { ( cd "$T/up" && git commit -q --allow-empty -m "d$RANDOM" && git push -q origin develop && git rev-parse HEAD ); }
sha=$(adv_dev)
row 'develop を開いていて、develop にマージした（コネクタ）' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":5}' "$(merged "$sha")")")" pulled
sha=$(adv_dev)
git -C "$T/me" checkout -q main
row 'main を開いていて、develop にマージした（コネクタ）' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":6}' "$(merged "$sha")")")" silent
git -C "$T/me" checkout -q develop
printf '#!/bin/sh\necho develop\n' > "$T/bin/gh"
row 'gh pr merge（gh pr view のマージ先が develop）' "$(res "$(run Bash '{"command":"gh pr merge 6 --merge"}')")" pulled
adv_dev >/dev/null
printf '#!/bin/sh\nexit 1\n' > "$T/bin/gh"
row 'gh pr view が失敗したら既定ブランチ（main）として扱う' "$(res "$(run Bash '{"command":"gh pr merge 7"}')")" silent
row 'gh pr merge -R 別リポ は手元を動かさない' "$(res "$(run Bash '{"command":"gh pr merge 7 -R O/other"}')")" silent

rm -rf "$T"
