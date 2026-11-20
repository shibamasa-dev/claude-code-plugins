#!/bin/bash
# Where the hooks keep state (_state.py): ${CLAUDE_PLUGIN_DATA}/<feature>, the one-time copy from the old
# ~/.claude/state/<feature>, and the CLI commands that run from Bash (which has no CLAUDE_PLUGIN_DATA of its own).
# HOME and CLAUDE_PLUGIN_DATA point at a temp directory, so the real ~/.claude is untouched.
set -u
D="$(cd "$(dirname "$0")/.." && pwd)"
IW="$D/hooks/issue-writeback.py"; HO="$D/hooks/handoff.py"; SV="$D/skills/session-wrap/scripts/survey.py"
FX="$D/tests/fixtures/state/issue-writeback/fx-sess.json"   # written by the hook before the move (fixtures/state/README.md)
T=$(mktemp -d "${TMPDIR:-/tmp}/state-dir.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
unset HANDOFF_STATE_DIR
mkdir -p "$T/bin"; printf '#!/bin/bash\necho "[]"\n' > "$T/bin/claude"; chmod +x "$T/bin/claude"   # survey.py asks `claude agents`
export PATH="$T/bin:$PATH"
row() { printf '  %-64s -> %-5s (expect %s)\n' "$1" "$2" "$3"; }
# fresh <name>: a new HOME and plugin data dir; sets H, DATA
fresh() { H="$T/$1/home"; DATA="$T/$1/data/workflow-test"; mkdir -p "$H"; }
old_iw() { mkdir -p "$H/.claude/state/issue-writeback" && cp "$FX" "$H/.claude/state/issue-writeback/"; }
iw_status() { HOME="$H" CLAUDE_PLUGIN_DATA="$DATA" python3 "$IW" status 2>&1; }
yes_no() { [ "$1" ] && echo yes || echo no; }

echo '=== migration (issue-writeback) ==='
fresh m1; old_iw
out=$(iw_status)
row 'old has data, new missing: copied to ${CLAUDE_PLUGIN_DATA}' "$(yes_no "$(ls "$DATA/issue-writeback/fx-sess.json" 2>/dev/null)")" yes
row '  ...and the hook reads it there' "$(yes_no "$(grep -o 'example-org/example-repo#7' <<<"$out")")" yes
row '  ...and the old directory stays as the backup' "$(yes_no "$(ls "$H/.claude/state/issue-writeback/fx-sess.json" 2>/dev/null)")" yes

fresh m2; old_iw; mkdir -p "$DATA/issue-writeback"; echo '{"issues": {}}' > "$DATA/issue-writeback/other.json"
iw_status >/dev/null
row 'new already has data: nothing copied over it' "$(yes_no "$(ls "$DATA/issue-writeback/fx-sess.json" 2>/dev/null)")" no

fresh m3
HOME="$H" CLAUDE_PLUGIN_DATA="$DATA" python3 -c "import sys; sys.path.insert(0, '$D/hooks'); import _state; _state.state_dir('issue-writeback', legacy='issue-writeback')"
row 'neither old nor new: nothing is created' "$(yes_no "$(ls -A "$T/m3" | grep data)")" no

fresh m4; old_iw
iw_status >/dev/null; rm -f "$DATA/issue-writeback/"*   # migrated, then everything in the new place is gone (GC, consumed)
iw_status >/dev/null
row 'new emptied later: the old copy is not pulled back' "$(yes_no "$(ls "$DATA/issue-writeback/fx-sess.json" 2>/dev/null)")" no

echo '=== which directory ==='
fresh w1; old_iw
HOME="$H" CLAUDE_PLUGIN_DATA="$T/w1/data/codex-inline" python3 "$IW" status >/dev/null 2>&1
row "another plugin's CLAUDE_PLUGIN_DATA is not used" "$(yes_no "$(ls -A "$T/w1/data" 2>/dev/null)")" no
row '  ...the fallback is ~/.claude/state/workflow/<feature>' "$(yes_no "$(ls "$H/.claude/state/workflow/issue-writeback/fx-sess.json" 2>/dev/null)")" yes

fresh s1; mkdir -p "$DATA/issue-writeback"; cp "$FX" "$DATA/issue-writeback/"
cmd=$(grep -o 'CLAUDE_PLUGIN_DATA="[^"]*" python3 "[^"]*survey.py"' "$D/skills/session-wrap/SKILL.md" | sed "s|\${CLAUDE_PLUGIN_DATA}|$DATA|; s|\${CLAUDE_PLUGIN_ROOT}|$D|")
out=$(cd "$T" && HOME="$H" bash -c "$cmd --session fx-sess --json" 2>&1)
row 'survey.py (as SKILL.md runs it) reads the new location' "$(yes_no "$(grep -o PENDING_ISSUE <<<"$out")")" yes

echo '=== commands printed for Bash carry the directory ==='
fresh c1; mkdir -p "$DATA/issue-writeback"; cp "$FX" "$DATA/issue-writeback/"
msg=""; for _ in 1 2 3; do msg+=$(printf '{"hook_event_name":"Stop","session_id":"fx-sess"}' | HOME="$H" CLAUDE_PLUGIN_DATA="$DATA" python3 "$IW"); done
dismiss=$(python3 -c 'import json,sys; r=json.loads(sys.stdin.read())["reason"]; print(next(l.strip() for l in r.splitlines() if " dismiss " in l))' <<<"$msg" | sed 's/<reason>/test/')
(cd "$T" && HOME="$H" bash -c "$dismiss" >/dev/null 2>&1)
got=$(python3 -c 'import json,sys; print("yes" if json.load(open(sys.argv[1]))["issues"]["example-org/example-repo#7"].get("dismissed") else "no")' "$DATA/issue-writeback/fx-sess.json")
row 'issue-writeback dismiss, run from Bash as printed, updates the hook state' "$got" yes

echo '=== handoff ==='
REPO="$T/repo"; mkdir -p "$REPO"; (cd "$REPO" && git init -q . && git remote add origin git@github.com:example-org/example-repo.git)
fresh h1
(cd "$REPO" && HOME="$H" HANDOFF_STATE_DIR="$H/.claude/state/handoff" python3 "$HO" write --entry example-org/example-repo#7 --state s --next n >/dev/null)
inj=$(printf '{"hook_event_name":"SessionStart","source":"startup","cwd":"%s"}' "$REPO" | HOME="$H" CLAUDE_PLUGIN_DATA="$DATA" python3 "$HO")
row 'old handoff is copied and injected from the new location' "$(yes_no "$(grep -o 'example-org/example-repo#7' <<<"$inj")")" yes
consume=$(grep -o 'CLAUDE_PLUGIN_DATA=[^`]* consume --entry' <<<"$inj" | head -1)
(cd "$REPO" && HOME="$H" bash -c "$consume example-org/example-repo#7" >/dev/null 2>&1)
row 'consume, run from Bash as printed, removes the entry there' "$(yes_no "$(cd "$REPO" && HOME="$H" CLAUDE_PLUGIN_DATA="$DATA" python3 "$HO" show 2>&1 | grep -o 'example-repo#7')")" no
row '  ...and the old copy is left as it was' "$(yes_no "$(grep -o 'example-repo#7' "$H"/.claude/state/handoff/*.json)")" yes

fresh h2
(cd "$REPO" && HOME="$H" HANDOFF_STATE_DIR="$H/.claude/state/handoff" python3 "$HO" write --entry example-org/example-repo#7 --state s --next n >/dev/null)
(cd "$REPO" && HOME="$H" CLAUDE_PLUGIN_DATA="$DATA" HANDOFF_STATE_DIR="$T/h2/override" python3 "$HO" show >/dev/null 2>&1)
row 'HANDOFF_STATE_DIR set: used as is, no migration' "$(yes_no "$(ls -A "$T/h2/data" 2>/dev/null)")" no
