#!/bin/bash
# Live check of skills/pr-review-triage/scripts/classify.sh: light vs heavy for real diffs.
# Each case is a branch in a throwaway clone of a local bare remote: real files, real commits, fed to the script the way
# SKILL.md step 2 does (`git diff --numstat origin/<base>...HEAD | bash classify.sh`). classify.sh calls neither gh nor
# git, so no fake gh is needed. HOME points at a temp directory so no global git config (renames, quotepath) leaks in;
# no network is used.
# Expected results come from SKILL.md step 2: heavy for a non-document file (no extension included) or a binary, a
# document under skills/ hooks/ agents/ commands/ rules/ .github/ or named SKILL.md / CLAUDE.md / AGENTS.md, more than
# 200 changed lines (added + deleted), or an empty diff; light for everything else. The "review it heavier" request and
# the review:light label are steps the skill takes around the script, not inputs to it, so they have no rows here.
set -u
CL="$(cd "$(dirname "$0")/.." && pwd)/skills/pr-review-triage/scripts/classify.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/classify.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
export HOME="$T/home" GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
mkdir -p "$HOME"
row() { printf '  %-62s -> %-5s (expect %s)\n' "$1" "$2" "$3"; }

git init -q --bare "$T/remote.git"
git -C "$T/remote.git" symbolic-ref HEAD refs/heads/main
R="$T/work"; git clone -q "$T/remote.git" "$R" 2>/dev/null
(cd "$R" && git checkout -q -b main && echo base > README.md && seq 1 300 > docs-long.md && mkdir -p docs \
  && echo guide > docs/guide.md && git add -A && git commit -qm init && git push -q -u origin main) \
  || { echo 'setup: could not push the base commit'; exit 1; }

# case <name>: start branch <name> from origin/main (the shell body that follows edits and commits in $R)
case_() { git -C "$R" checkout -q -B "$1" origin/main; }
commit() { git -C "$R" add -A && git -C "$R" commit -qm "$1" --allow-empty; }
# verdict: line 1 of classify.sh's output for the current branch's diff against origin/main
verdict() { (cd "$R" && git diff --numstat origin/main...HEAD | bash "$CL" | head -1); }
is() { [ "$1" = "$2" ] && echo ok || echo "bad: $1"; }

echo '=== documents only ==='
for ext in md markdown txt rst adoc; do
  case_ "doc-$ext"; echo x > "$R/docs/note.$ext"; commit "doc $ext"
  row "a new .$ext document -> light" "$(is "$(verdict)" light)" ok
done
case_ doc-near-skills; echo x > "$R/docs/skills-guide.md"; commit near
row 'docs/skills-guide.md (skills in a name, not a directory) -> light' "$(is "$(verdict)" light)" ok
case_ doc-near-name; echo x > "$R/docs/CLAUDE-notes.md"; commit near
row 'docs/CLAUDE-notes.md (not exactly CLAUDE.md) -> light' "$(is "$(verdict)" light)" ok

echo
echo '=== non-document files ==='
case_ code; echo 'print(1)' > "$R/tool.py"; commit code
row 'a .py file -> heavy' "$(is "$(verdict)" heavy)" ok
case_ config; echo '{}' > "$R/settings.json"; commit config
row 'a .json config file -> heavy' "$(is "$(verdict)" heavy)" ok
case_ noext; echo '*.log' > "$R/.gitignore"; commit noext
row 'a file with no extension (.gitignore) -> heavy' "$(is "$(verdict)" heavy)" ok
case_ binary; printf 'a\000b' > "$R/docs/data.txt"; commit binary
row 'a binary file with a document extension -> heavy' "$(is "$(verdict)" heavy)" ok

echo
echo '=== behavior-defining documents ==='
for d in skills hooks agents commands rules .github; do
  case_ "path-${d#.}"; mkdir -p "$R/$d"; echo x > "$R/$d/x.md"; commit "path $d"
  row "a document under $d/ -> heavy" "$(is "$(verdict)" heavy)" ok
done
case_ path-nested; mkdir -p "$R/plugins/p/skills/s"; echo x > "$R/plugins/p/skills/s/notes.md"; commit nested
row 'a document under a nested skills/ directory -> heavy' "$(is "$(verdict)" heavy)" ok
for n in SKILL.md CLAUDE.md AGENTS.md; do
  case_ "name-${n%.md}"; echo x > "$R/docs/$n"; commit "name $n"
  row "docs/$n (named, outside those directories) -> heavy" "$(is "$(verdict)" heavy)" ok
done

echo
echo '=== changed lines (added + deleted) ==='
case_ lines-200; seq 1 200 > "$R/docs/new.md"; commit 200
row '200 added lines -> light' "$(is "$(verdict)" light)" ok
case_ lines-201; seq 1 201 > "$R/docs/new.md"; commit 201
row '201 added lines -> heavy' "$(is "$(verdict)" heavy)" ok
# docs-long.md has lines 1..300: keep 1..200 (lines 201..300 deleted) and append new lines
case_ lines-mixed-200; (cd "$R" && seq 1 200 > docs-long.md && seq 1 100 | sed 's/^/n/' >> docs-long.md); commit mixed
row '100 deleted + 100 added in one file (200) -> light' "$(is "$(verdict)" light)" ok
case_ lines-mixed-201; (cd "$R" && seq 1 200 > docs-long.md && seq 1 101 | sed 's/^/n/' >> docs-long.md); commit mixed
row '100 deleted + 101 added in one file (201) -> heavy' "$(is "$(verdict)" heavy)" ok
case_ lines-split; seq 1 150 > "$R/docs/a.md"; seq 1 51 > "$R/docs/b.md"; commit split
row '150 + 51 lines across two documents (201) -> heavy' "$(is "$(verdict)" heavy)" ok

echo
echo '=== empty diff ==='
case_ empty; commit empty
row 'a branch whose diff is empty -> heavy' "$(is "$(verdict)" heavy)" ok
