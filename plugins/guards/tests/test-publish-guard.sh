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
json.dump({"github.com/acme/widgets": {"visibility": "public", "at": now},
           "github.com/acme/vault": {"visibility": "private", "at": now}},
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
  row "gh issue create -R acme/widgets -t \"Add\" --body-file \"$W/acme-build-tmp/body.md\"" 'path matches, file text is clean' 'allow'
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
echo '=== B2: a body file the same command writes (the copy on disk is from before the command) ==='
printf 'old text with acme-internal\n' > "$PROBE_CWD/stale.md"
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row $'cat > stale.md <<\'EOF\'\nclean text\nEOF\ngh issue comment 12 -R acme/widgets --body-file stale.md' 'stale copy has the hit, heredoc writes clean text' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row 'printf "clean text\n" > stale.md && gh issue comment 12 -R acme/widgets --body-file stale.md' 'stale copy has the hit, printf writes clean text' 'allow'
printf 'clean\n' > "$PROBE_CWD/fresh.md"
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file' \
  row 'echo "see acme-internal" > fresh.md && gh issue comment 12 -R acme/widgets --body-file fresh.md' 'clean copy on disk, echo writes the hit' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='written in the same command|earlier command' \
  row 'python3 gen.py > fresh.md && gh issue comment 12 -R acme/widgets --body-file fresh.md' 'file written by a program: not checked, said so' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='$(< body.md)' \
  row 'gh issue comment 12 -R acme/widgets --body "$(< body.md)"' 'body read with $(< file)' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='heredoc|separate command' \
  row $'gh issue comment 12 -R acme/widgets -b "ok" && cat > notes.md <<\'EOF\'\nacme-internal\nEOF' 'heredoc that does not feed gh: deny says to split the command' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file' \
  row 'echo "more" >> stale.md && gh issue comment 12 -R acme/widgets --body-file stale.md' 'append keeps the text already in the file' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file' \
  row 'for n in 1 2; do gh issue comment $n -R acme/widgets --body-file fresh.md; echo "see acme-internal" > fresh.md; done' 'file written further on in the command (a loop): that text is checked too' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row 'gh issue comment 12 -R acme/widgets --body-file fresh.md && echo "all clean" > fresh.md' 'file written further on with clean text' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file' \
  row 'echo "> see acme-internal" > fresh.md && gh issue comment 12 -R acme/widgets --body-file fresh.md' 'echo argument that starts with > (a quoted line)' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file' \
  row 'printf "> quoted acme-internal\n" > fresh.md && gh issue comment 12 -R acme/widgets --body-file fresh.md' 'printf argument that starts with >' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--body-file' \
  row 'echo "<< acme-internal" > fresh.md && gh issue comment 12 -R acme/widgets --body-file fresh.md' 'echo argument that starts with <<' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='$(cat fresh.md)' \
  row 'echo "see acme-internal" > fresh.md && gh issue comment 12 -R acme/widgets -b "$(cat fresh.md)"' '$(cat file) of a file the command wrote: the written text' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row 'printf "clean text\n" > stale.md && gh issue comment 12 -R acme/widgets -b "$(cat stale.md)"' '$(cat file): stale copy has the hit, printf writes clean text' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='heredoc' \
  row $'gh issue comment 12 -R acme/widgets --body-file - <<EOF\nfirst\n EOF\nsee acme-internal\nEOF' 'heredoc: an indented look-alike line does not end the body' 'deny'
printf 'built by acme-build\n' > "$PROBE_CWD/acme-build-notes.md"
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["acme-build"]' PARTS='line 1' \
  row 'gh issue comment 12 -R acme/widgets --body-file acme-build-notes.md' 'file name matches a pattern: the message does not repeat it' 'deny'
printf 'clean\n' > "$PROBE_CWD/s1.md"; printf 'clean\n' > "$PROBE_CWD/c.md"; mkdir -p "$PROBE_CWD/out"; printf 'clean\n' > "$PROBE_CWD/out/note.md"
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='written in the same command|earlier command' \
  row 'cp note.md s1.md && gh issue create -R acme/widgets -t T --body-file s1.md' 'body file written by cp: not checked, said so' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='written in the same command|earlier command' \
  row 'mv note.md s1.md && gh issue create -R acme/widgets -t T --body-file s1.md' 'body file written by mv' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='written in the same command|earlier command' FORBID='' \
  row "sed -i '' 's/clean/acme-internal/' s1.md && gh issue create -R acme/widgets -t T --body-file s1.md" 'body file rewritten by sed -i' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='written in the same command|earlier command' \
  row 'install -m 644 note.md s1.md && gh issue create -R acme/widgets -t T --body-file s1.md' 'body file written by install' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='written in the same command|earlier command' \
  row 'dd if=note.md of=s1.md && gh issue create -R acme/widgets -t T --body-file s1.md' 'body file written by dd of=' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='written in the same command|earlier command' \
  row 'cp note.md out && gh issue create -R acme/widgets -t T --body-file out/note.md' 'body file written by cp into its directory' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row 'cp note.md s1.md && gh issue create -R acme/widgets -t T --body-file c.md' 'cp of an unrelated file: the clean body file stays silent' 'allow'
mkfifo "$PROBE_CWD/pipe.md"
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='could not be read' \
  row 'gh issue comment 12 -R acme/widgets --body-file pipe.md' 'body file is a named pipe: not opened' 'note'

echo
echo '=== B3: other spellings that publish text ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--comment|gh issue close' \
  row 'gh issue close 12 -R acme/widgets --comment "fixed in acme-internal"' 'gh issue close --comment' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='--comment|gh pr close' \
  row 'gh pr close 7 -R acme/widgets -c "moved to acme-internal"' 'gh pr close -c' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='gh issue comment|public repo acme/widgets' \
  row 'gh issue -R acme/widgets comment 12 -b "see acme-internal"' 'flag between the group and the verb' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='body' \
  row 'gh api repos/acme/widgets/pulls/7/comments/55/replies -f body="as in acme-internal"' 'gh api review-comment reply endpoint' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='body' \
  row 'gh api repos/acme/widgets/pulls/7/reviews/9/events -f event=COMMENT -f body="acme-internal"' 'gh api review submit endpoint' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='public repo acme/widgets' \
  row 'cd /tmp && gh pr comment https://github.com/acme/widgets/pull/3 --body "acme-internal"' 'PR given by URL names the repo' 'deny'

CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|do not name one' \
  row 'gh issue edit https://github.com/acme/vault/issues/1 https://github.com/acme/widgets/issues/2 --body "acme-internal"' 'issues of two repos by URL: unknown, with a note' 'note'

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

CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='labels' \
  mrow '{"tool_name":"mcp__gh__issue_write","tool_input":{"method":"update","owner":"acme","repo":"widgets","issue_number":12,"labels":["acme-internal"]}}' 'MCP issue_write: labels are read' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='issue_fields' \
  mrow '{"tool_name":"mcp__gh__issue_write","tool_input":{"method":"update","owner":"acme","repo":"widgets","issue_number":12,"issue_fields":[{"field_name":"Team","field_option_name":"acme-internal"}]}}' 'MCP issue_write: issue field option names are read' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='issue_fields' \
  mrow '{"tool_name":"mcp__gh__issue_write","tool_input":{"method":"update","owner":"acme","repo":"widgets","issue_number":12,"issue_fields":[{"field_name":"Note","value":"acme-internal"}]}}' 'MCP issue_write: issue field values are read' 'deny'
: > "$GH_LOG"
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|names no owner / repo' \
  mrow '{"tool_name":"mcp__gh__add_issue_comment","tool_input":{"issue_number":12,"body":"acme-internal"}}' 'MCP call without owner / repo' 'note'
printf '  %s -> %s (expect %s)\n' 'no owner / repo: nothing is looked up' "$([ -s "$GH_LOG" ] && echo asked || echo silent)" 'silent'

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
git -C "$W/onerepo" config remote.upstream.gh-resolved base
PROBE_CWD="$W/onerepo" CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 \
  row 'gh issue create -t "Fix" -b "acme-internal"' 'gh-resolved = base: that remote (private)' 'allow'
git -C "$W/onerepo" config remote.upstream.gh-resolved acme/widgets
PROBE_CWD="$W/onerepo" CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='public repo acme/widgets' \
  row 'gh issue create -t "Fix" -b "acme-internal"' 'gh-resolved names another repo: that repo' 'deny'
PROBE_CWD="$W/onerepo" CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|GraphQL' \
  row 'gh api graphql -f query="mutation { addComment(input: {body: \"acme-internal\"}) { clientMutationId } }"' 'gh api graphql: target not readable' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|acme/offline' \
  row 'gh issue create -R acme/offline -t "Fix" -b "acme-internal"' 'visibility lookup fails' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FAKE_VISIBILITY=public PARTS='public repo acme/fresh' \
  row 'gh issue create -R acme/fresh -t "Fix" -b "acme-internal"' 'cache miss: asked once, public' 'deny'
printf '  %s -> %s (expect %s)\n' 'the lookup names github.com whatever GH_HOST says' "$(grep -q -- '--hostname github.com repos/acme/fresh' "$GH_LOG" && echo pinned || echo unpinned)" 'pinned'
printf '  %s -> %s (expect %s)\n' 'cache miss made one lookup' "$(grep -c 'repos/acme/fresh' "$GH_LOG" | sed 's/^1$/one/')" 'one'
python3 - <<'PY'
import json, os
p = os.path.join(os.environ["CLAUDE_PLUGIN_DATA"], "repo-visibility.json")
d = json.load(open(p)); d["github.com/acme/damaged"] = {"visibility": "private", "at": "yesterday"}
d["github.com/acme/listed"] = {"visibility": ["private"], "at": 0}; json.dump(d, open(p, "w"))
PY
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FAKE_VISIBILITY=public PARTS='public repo acme/damaged' \
  row 'gh issue create -R acme/damaged -t "Fix" -b "acme-internal"' 'damaged cache entry: treated as a miss' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FAKE_VISIBILITY=public PARTS='public repo acme/listed' \
  row 'gh issue create -R acme/listed -t "Fix" -b "acme-internal"' 'cache entry whose visibility is not a string: a miss' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='[]' FORBID='' \
  row 'gh issue create -R acme/widgets -t "Fix" --body-file missing.md' 'empty array: off and silent' 'allow'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["acme-internal(?i)", "acme-internal"]' PARTS='pattern #1 is not a valid regex|pattern #2 of 2' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "acme-internal"' 'flag not at the start of a pattern: skipped, nothing on stderr' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["a{99999999999999999999}", "acme-internal"]' PARTS='pattern #1 is not a valid regex|pattern #2 of 2' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "acme-internal"' 'pattern with a repeat count too large to compile: skipped' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='could not be read|visibility unknown' \
  row 'gh issue create -R acme/widgets -t "Fix" --body-file missing.md; gh issue create -t "Fix" -b "acme-internal"' 'two gh calls, a note each: both are said' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 PARTS='visibility unknown|mixes a placeholder' \
  row 'gh api "repos/{owner}/widgets/issues/1/comments" -f body="acme-internal"' 'API path with one placeholder: repo unknown' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='[""]' PARTS='pattern #1 matches the empty string' \
  row 'gh pr comment 1 -R acme/widgets --body "hello world"' 'pattern that matches the empty string: skipped, nothing denied' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["acme-internal|", "acme-build"]' PARTS='pattern #1 matches the empty string|pattern #2 of 2' FORBID='acme-internal|acme-build|' \
  row 'gh pr comment 1 -R acme/widgets --body "from acme-build"' 'pattern with a stray |: skipped, the rest apply' 'deny'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='acme-internal' PARTS='not a JSON array' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "acme-internal"' 'setting is not a JSON array' 'note'
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS='["acme-(", "acme-internal"]' PARTS='pattern #1 is not a valid regex|pattern #2 of 2' \
  row 'gh issue create -R acme/widgets -t "Fix" -b "acme-internal"' 'one invalid pattern: skipped, the rest apply' 'deny'

echo
echo '=== F: the other rules are unaffected ==='
CLAUDE_PLUGIN_OPTION_PUBLISH_PATTERNS=$P1 FORBID='' \
  row 'gh issue create -R acme/vault -t "Fix" -b "acme-internal"; rm -rf ~' 'a deny from another rule still wins' 'deny'

rm -rf "$W"
