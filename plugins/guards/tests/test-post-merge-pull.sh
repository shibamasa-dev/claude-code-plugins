#!/bin/bash
# Measure git-freshness.py's post-merge-pull: after a merge, does it bring the local merge-target branch up to date?
# Does a GitHub connector merge (mcp__*__merge_pull_request) act only when the cwd's origin is the same repo?
# origin URLs use the github.com form and are redirected to a local bare repo with insteadOf (no network access).
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/git-freshness.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/pmp.XXXX")
export HOME="$T" GIT_CONFIG_NOSYSTEM=1
git config --global user.email t@example.com; git config --global user.name t
git config --global init.defaultBranch main
git config --global advice.detachedHead false
git config --global url."file://$T/origin.git".insteadOf https://github.com/O/R.git
# Fake gh (so the real gh doesn't query GitHub). By default it fails = the merge target is unknown
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
# Shape of the connector result ([{"type":"text","text":"{\"sha\":...}"}])
merged() { python3 -c 'import json,sys; print(json.dumps([{"type":"text","text":json.dumps({"sha":sys.argv[1],"merged":True})}]))' "$1"; }
res() { case "$1" in *⚠️*) echo warned ;; *Auto-pulled*) echo pulled ;; '') echo silent ;; *) echo other ;; esac; }
row() { printf '  %-58s -> %-7s (expect %s)\n' "$1" "$2" "$3"; }

advance
row 'after gh pr merge, pull if main is behind' "$(res "$(run Bash '{"command":"gh pr merge 3 --squash"}')")" pulled
row 'say nothing once caught up' "$(res "$(run Bash '{"command":"gh pr merge 3 --squash"}')")" silent
advance
row 'connector merge (same repo, owner case ignored)' "$(res "$(run mcp__github__merge_pull_request '{"owner":"o","repo":"r","pullNumber":3}')")" pulled
advance
row 'connector merge (another repo) leaves the checkout alone' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"other","pullNumber":3}')")" silent
row '  main stays behind then' "$( [ "$(behind)" -gt 0 ] && echo behind || echo synced)" behind
row 'other connector tools are ignored' "$(res "$(run mcp__github__pull_request_read '{"owner":"O","repo":"R","pullNumber":3}')")" silent
( cd "$T/up" && echo a > README && git add README && git commit -q -m readme && git push -q origin main )
git -C "$T/me" pull -q --ff-only origin main
echo local > "$T/me/README"   # local uncommitted change
( cd "$T/up" && echo b > README && git commit -q -am readme2 && git push -q origin main )
row 'local changes blocking ff: leave alone and report' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":4}')")" warned
git -C "$T/me" checkout -q -b feat
row 'does nothing on a branch other than the target (main)' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":4}')")" silent

# A PR whose merge target is develop (different from the default branch main)
git -C "$T/me" checkout -q -f main && git -C "$T/me" checkout -q -- . 2>/dev/null
( cd "$T/up" && git pull -q origin main && git checkout -q -b develop && git commit -q --allow-empty -m d0 && git push -q origin develop )
git -C "$T/me" fetch -q origin && git -C "$T/me" checkout -q -b develop origin/develop
adv_dev() { ( cd "$T/up" && git commit -q --allow-empty -m "d$RANDOM" && git push -q origin develop && git rev-parse HEAD ); }
sha=$(adv_dev)
row 'develop checked out, merged into develop (connector)' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":5}' "$(merged "$sha")")")" pulled
sha=$(adv_dev)
git -C "$T/me" checkout -q main
row 'main checked out, merged into develop (connector)' "$(res "$(run mcp__github__merge_pull_request '{"owner":"O","repo":"R","pullNumber":6}' "$(merged "$sha")")")" silent
git -C "$T/me" checkout -q develop
printf '#!/bin/sh\necho develop\n' > "$T/bin/gh"
row 'gh pr merge (gh pr view says the target is develop)' "$(res "$(run Bash '{"command":"gh pr merge 6 --merge"}')")" pulled
adv_dev >/dev/null
printf '#!/bin/sh\nexit 1\n' > "$T/bin/gh"
row 'if gh pr view fails, treat as the default branch (main)' "$(res "$(run Bash '{"command":"gh pr merge 7"}')")" silent
row 'gh pr merge -R another repo leaves the checkout alone' "$(res "$(run Bash '{"command":"gh pr merge 7 -R O/other"}')")" silent
printf '#!/bin/sh\necho develop\n' > "$T/bin/gh"
row 'gh pr merge -R github.com/O/R (same repo with host)' "$(res "$(run Bash '{"command":"gh pr merge 7 -R github.com/O/R"}')")" pulled
adv_dev >/dev/null
row 'gh pr merge -R otherhost/O/R leaves the checkout alone' "$(res "$(run Bash '{"command":"gh pr merge 8 -R ghe.example.com/O/R"}')")" silent

row 'gh pr merge <URL of a PR in another repo>: no change' "$(res "$(run Bash '{"command":"gh pr merge https://github.com/O/other/pull/9"}')")" silent
row 'gh pr merge <URL of a PR in the same repo>' "$(res "$(run Bash '{"command":"gh pr merge https://github.com/O/R/pull/9"}')")" pulled

# A GitHub Enterprise clone, pointed at with -R OWNER/REPO without the host
printf '#!/bin/sh\necho develop\n' > "$T/bin/gh"
git config --global --add url."file://$T/origin.git".insteadOf https://ghe.example.com/O/R.git
git -C "$T/me" remote set-url origin https://ghe.example.com/O/R.git
adv_dev >/dev/null
row 'GHE clone: gh pr merge -R O/R (host omitted)' "$(res "$(run Bash '{"command":"gh pr merge 11 -R O/R"}')")" pulled
git -C "$T/me" remote set-url origin https://github.com/O/R.git

# The default branch was changed to develop on origin (local origin/HEAD stays main; fetch doesn't update it)
printf '#!/bin/sh\nexit 1\n' > "$T/bin/gh"
git -C "$T/origin.git" symbolic-ref HEAD refs/heads/develop
adv_dev >/dev/null
row '  local origin/HEAD is still the old one (main)' "$(git -C "$T/me" symbolic-ref --short refs/remotes/origin/HEAD | sed 's#^origin/##')" main
row 'target unknown: use the current origin default (develop)' "$(res "$(run Bash '{"command":"gh pr merge 10"}')")" pulled

rm -rf "$T"
