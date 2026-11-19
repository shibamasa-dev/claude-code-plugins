#!/bin/bash
# Measure publish-guard (bash-guard.py's check of issue / PR text against the setting publish_patterns).
# The blocked names are made up (acme-internal, acme-build). Visibility comes from a seeded cache file under a
# temporary CLAUDE_PLUGIN_DATA; a fake `gh` on PATH logs every call and fails, so nothing reaches the network
# and "no lookup" can be asserted.
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"
T0=${TMPDIR:-/tmp}; W=$(mktemp -d "${T0%/}/publish-guard.XXXX")
export CLAUDE_PLUGIN_DATA="$W/data" GH_LOG="$W/gh.log" PROBE_CWD="$W/work"
mkdir -p "$CLAUDE_PLUGIN_DATA" "$W/bin" "$PROBE_CWD" "$W/acme-build-tmp"
unset GH_REPO
printf '#!/bin/bash\necho "$*" >> "$GH_LOG"\n[ -n "${FAKE_VISIBILITY:-}" ] && { echo "$FAKE_VISIBILITY"; exit 0; }\nexit 1\n' > "$W/bin/gh"
chmod +x "$W/bin/gh"
export PATH="$W/bin:$PATH"
python3 - <<'PY'
import json, os, time
now = int(time.time())
json.dump({"acme/widgets": {"visibility": "public", "at": now}, "acme/vault": {"visibility": "private", "at": now}},
          open(os.path.join(os.environ["CLAUDE_PLUGIN_DATA"], "repo-visibility.json"), "w"))
PY
# Body files (line 3 of body.md is Japanese text around the blocked name)
printf 'Steps to reproduce\n\n社内の acme-internal 環境で再現\n' > "$PROBE_CWD/body.md"
printf 'copied from acme-internal\n' > "$PROBE_CWD/note.md"
printf 'nothing private here\n' > "$W/acme-build-tmp/body.md"
printf '{"body": "acme-\\u0069nternal", "event": "COMMENT"}\n' > "$PROBE_CWD/payload.json"

# probe <payload JSON>: prints one word. allow = no output / note = allowed with additionalContext / deny.
# PARTS (|-separated) must all appear in the hook's message, and FORBID (|-separated) must not appear anywhere
# in its output; otherwise the word is missing / leak.
probe() {
  python3 - "$1" <<'PY'
import json, os, subprocess, sys
p = subprocess.run(["python3", os.environ["HOOK"]], input=sys.argv[1], capture_output=True, text=True)
raw = p.stdout.strip()
if p.returncode != 0 or p.stderr.strip():
    print("crash"); raise SystemExit
forbid = [x for x in os.environ.get("FORBID", "").split("|") if x]
if any(x in raw for x in forbid):
    print("leak"); raise SystemExit
if not raw:
    print("allow"); raise SystemExit
out = json.loads(raw).get("hookSpecificOutput", {})
decision = out.get("permissionDecision")
text = (out.get("permissionDecisionReason") or "") + (out.get("additionalContext") or "")
if any(x not in text for x in os.environ.get("PARTS", "").split("|") if x):
    print("missing"); raise SystemExit
print(decision or "note")
PY
}
bash_payload() { python3 -c 'import json,os,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]},"cwd":os.environ["PROBE_CWD"]}))' "$1"; }
# row <command> <label> <expect> : a Bash tool call
row() { printf '  %s -> %s (expect %s)\n' "$2" "$(probe "$(bash_payload "$1")")" "$3"; }
# mrow <payload JSON> <label> <expect> : any tool call
mrow() { printf '  %s -> %s (expect %s)\n' "$2" "$(probe "$1")" "$3"; }
P1='["acme-internal"]'
export FORBID='acme-internal|acme-build'

echo '=== A: the decision follows the target repo (issue #105 Examples, rows 1-3) ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='pattern #1 of 1|--body|public repo acme/widgets' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "see acme-internal/tools"' 'hit, public repo' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row 'gh issue create -R acme/vault -t "Fix" -b "see acme-internal/tools"' 'hit, private repo: silent' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='' FORBID='' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "see acme-internal/tools"' 'guard off (empty setting): silent' 'allow'

echo
echo '=== B: where the text comes from ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file|line 3' \
  row 'gh issue comment 12 -R acme/widgets --body-file body.md' 'body file, Japanese text on line 3' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='body=@note.md' \
  row 'gh api -X PATCH repos/acme/widgets/issues/comments/99 -F body=@note.md' 'gh api -F body=@file' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["/srv/acme-build"]' PARTS='heredoc' \
  row $'gh pr create -R acme/widgets -t "Add" --body "$(cat <<\'EOF\'\nSummary\nbuilt in /srv/acme-build/out\nEOF\n)"' 'heredoc inside $(cat <<EOF)' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["acme-build"]' \
  row "gh issue create -R acme/widgets -t \"Add\" --body-file $W/acme-build-tmp/body.md" 'path matches, file text is clean' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='heredoc' \
  row $'cat > later.md <<\'EOF\'\nsee acme-internal\nEOF\ngh issue create -R acme/widgets -t "Fix" --body-file later.md' 'body file written by a heredoc in the same command' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='heredoc|public repo acme/widgets' \
  row $'gh issue comment 1 -R acme/vault -b "ok" && gh issue comment 2 -R acme/widgets --body-file - <<\'EOF\'\nsee acme-internal\nEOF' 'heredoc with two gh calls: judged for the public one too' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file|could not be read' \
  row 'gh issue create -R acme/widgets -t "Fix" --body-file missing.md' 'body file that does not exist' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='body' \
  row 'gh api "https://api.github.com/repos/acme/widgets/issues/12/comments?per_page=1" -f body="acme-internal"' 'gh api with a full URL and a query string' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='stdin|not checked' FORBID='' \
  row 'echo acme-internal | gh issue comment 12 -R acme/widgets --body-file -' 'body piped from another command' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--input' \
  row 'gh api repos/acme/widgets/pulls/1/reviews --input payload.json' 'gh api --input: JSON is decoded before matching' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='comments[][body]' \
  row "gh api repos/acme/widgets/pulls/1/reviews -f 'comments[][path]=a.py' -f 'comments[][body]=acme-internal' -f event=COMMENT" 'gh api nested field comments[][body]' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='public repo acme/widgets' \
  row 'GH_REPO=acme/vault gh issue edit https://github.com/acme/widgets/issues/1 --body acme-internal' 'issue given by URL beats GH_REPO' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='public repo acme/widgets' \
  row 'GH_REPO=acme/vault gh issue edit --add-label bug https://github.com/acme/widgets/issues/1 --body acme-internal' 'URL selector after a flag that takes a value' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body' \
  row 'gh pr review 7 -R acme/widgets -a -b "lgtm, as in acme-internal"' 'gh pr review: -a is a switch, the body is still read' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--title' \
  row 'gh pr edit 7 -R acme/widgets --title="Port acme-internal"' 'title in the --flag=value form' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body' \
  row 'B="see acme-internal"; gh issue comment 12 -R acme/widgets -b "$B"' 'variable assigned in the same command' 'deny'

echo
echo '=== C: only commands that publish text are read ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FORBID='' \
  row "gh issue view 12 -R acme/widgets --json body --jq '.body | contains(\"acme-internal\")'" 'gh issue view (a read)' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FORBID='' \
  row 'gh api repos/acme/widgets/issues/12 --jq ".body | test(\"acme-internal\")"' 'gh api GET' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FORBID='' \
  row $'cat > notes.md <<\'EOF\'\nacme-internal\nEOF' 'heredoc with no gh command' 'allow'
: > "$GH_LOG"
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row 'gh issue create -R acme/unseen -t "Fix" -b "nothing private"' 'clean text to an uncached repo' 'allow'
printf '  %s -> %s (expect %s)\n' 'clean text asks nobody for the visibility' "$([ -s "$GH_LOG" ] && echo asked || echo silent)" 'silent'

echo
echo '=== D: MCP tools ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='pattern #1 of 1|body|add_issue_comment' \
  mrow '{"tool_name":"mcp__gh__add_issue_comment","tool_input":{"owner":"acme","repo":"widgets","issue_number":12,"body":"acme-internal"}}' 'MCP add_issue_comment, public repo' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FORBID='' \
  mrow '{"tool_name":"mcp__gh__get_file_contents","tool_input":{"owner":"acme","repo":"widgets","body":"acme-internal"}}' 'MCP tool that is not a text write' 'allow'

echo
echo '=== E: cannot determine -> allow, with a note ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|pattern #1' \
  row 'gh issue create -t "Fix" -b "acme-internal"' 'no repo resolvable (no github.com remote)' 'note'
git -C "$W" init -q -b main onerepo && git -C "$W/onerepo" remote add origin https://github.com/acme/widgets.git
PROBE_CWD="$W/onerepo" CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='public repo acme/widgets' \
  row 'gh issue create -t "Fix" -b "acme-internal"' 'repo from the only GitHub remote of the directory' 'deny'
git -C "$W/onerepo" remote add upstream git@github.com:acme/vault.git
PROBE_CWD="$W/onerepo" CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|several GitHub remotes' \
  row 'gh issue create -t "Fix" -b "acme-internal"' 'two GitHub remotes, none marked gh-resolved' 'note'
PROBE_CWD="$W/onerepo" CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|GraphQL' \
  row 'gh api graphql -f query="mutation { addComment(input: {body: \"acme-internal\"}) { clientMutationId } }"' 'gh api graphql: target not readable' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|acme/offline' \
  row 'gh issue create -R acme/offline -t "Fix" -b "acme-internal"' 'visibility lookup fails' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FAKE_VISIBILITY=public PARTS='public repo acme/fresh' \
  row 'gh issue create -R acme/fresh -t "Fix" -b "acme-internal"' 'cache miss: asked once, public' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='acme-internal' PARTS='not a JSON array' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "acme-internal"' 'setting is not a JSON array' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["acme-(", "acme-internal"]' PARTS='pattern #1 is not a valid regex|pattern #2 of 2' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "acme-internal"' 'one invalid pattern: skipped, the rest apply' 'deny'

echo
echo '=== F: the other rules are unaffected ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FORBID='' \
  row 'gh issue create -R acme/vault -t "Fix" -b "acme-internal"; rm -rf ~' 'a deny from another rule still wins' 'deny'

rm -rf "$W"
