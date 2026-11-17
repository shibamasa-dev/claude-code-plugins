#!/bin/bash
# Live check of commit_gate.py against a throwaway origin (bare repo) and a clone of it, in a path with a space and
# non-ASCII characters. Event payloads come from fixtures/commit-gate/, recorded from a real headless session
# (Claude Code 2.1.326) with a probe plugin; the session-specific fields (session_id, prompt_id, cwd) are filled in here.
# CLAUDE_PLUGIN_DATA and HOME point at the temp directory, so real state is untouched (no network access).
# COMMIT_GATE_HOOK=<path> runs the rows against another copy of the hook (used to show each row fails without its logic).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="${COMMIT_GATE_HOOK:-$HERE/../hooks/commit_gate.py}"
FIX="$HERE/fixtures/commit-gate"
T=$(mktemp -d "${TMPDIR:-/tmp}/cg.XXXX")
# Guard: every git write below happens under $T (an empty or unexpected path would commit into the caller's repo)
case "$T" in ""|/) echo "mktemp failed" >&2; exit 1 ;; esac
[ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
export CLAUDE_PLUGIN_DATA="$T/data" HOME="$T" GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
unset CLAUDE_PLUGIN_OPTION_COMMIT_GATE CLAUDE_PLUGIN_OPTION_COMMIT_GATE_VERIFIERS GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
O="$T/origin.git"; SEED="$T/seed"; W="$T/作業 リポ"

in_dir() {  # in_dir <dir>: cd there and confirm that git sees exactly that directory as the top level
  cd "$1" || exit 1
  [ "$(git rev-parse --show-toplevel)" = "$(pwd -P)" ] || { echo "not at the top of $1 (pwd=$(pwd))" >&2; exit 1; }
}
git init -q --bare -b main "$O"
git clone -q "$O" "$SEED" 2>/dev/null; in_dir "$SEED"
printf 'def add(a, b):\n    return a + b\n' > m.py; git add m.py; git commit -qm init; git push -q origin main
git clone -q "$O" "$W"; in_dir "$W"

# set_repo_cfg <json|-> : put .claude/verification.json on origin's main (- removes it), then fetch it into the clone
set_repo_cfg() {
  ( in_dir "$SEED"; mkdir -p .claude
    if [ "$1" = - ]; then git rm -q --ignore-unmatch .claude/verification.json; else printf '%s\n' "$1" > .claude/verification.json; git add .claude; fi
    git commit -qm cfg --allow-empty; git push -q origin main )
  git -C "$W" fetch -q origin
}
reset() { rm -rf "$CLAUDE_PLUGIN_DATA"; in_dir "$W"; git checkout -q -- . ; git clean -qfd; }

# ev <fixture|-> <session> <prompt> [key=json ...] : build the event (fixture + overrides) and run the hook
ev() {
  python3 - "$FIX" "$W" "$@" <<'PY' | python3 "$HOOK"
import json, sys
fix, cwd, name, sid, pid, *kv = sys.argv[1:]
d = json.load(open(f"{fix}/{name}.json")) if name != "-" else {}
d.update(session_id=sid, prompt_id=pid, cwd=cwd)
for x in kv:
    k, v = x.split("=", 1)
    d[k] = json.loads(v)
print(json.dumps(d))
PY
}
j() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
review() { ev upe-code-review "$1" "$2" >/dev/null; }                                # typed /code-review
skill() { ev post-skill-code-review "$1" "$2" "tool_input={\"skill\":$(j "$3")}" >/dev/null; }  # Skill tool
stop() { ev - "$1" "$2" 'hook_event_name="Stop"' 'stop_hook_active=false' >/dev/null; }
LOG="$CLAUDE_PLUGIN_DATA/commit-gate/log.jsonl"
loglines() { [ -f "$LOG" ] && wc -l < "$LOG" | tr -d ' ' || echo 0; }
lastlog() { tail -1 "$LOG" | python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1]))' "$1"; }
# commit <session> <prompt> <bash command> -> deny (the hook's JSON) or, from the decision it logged:
# block (would_block in observe) / stale / release / nogate / unparsed / allow (allow, explained, or nothing logged)
commit() {
  n0=$(loglines)
  out=$(ev - "$1" "$2" 'hook_event_name="PreToolUse"' 'tool_name="Bash"' "tool_input={\"command\":$(j "$3")}")
  case "$out" in *'"permissionDecision": "deny"'*) echo deny; return ;; esac
  [ "$(loglines)" = "$n0" ] && { echo allow; return; }
  case "$(lastlog decision)" in
    would_block) echo block ;; stale) echo stale ;; released) echo release ;; nogate) echo nogate ;;
    unparsed) echo unparsed ;; allow|explained) echo allow ;; *) echo "other:$(lastlog decision)" ;;
  esac
}
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }
TR='Verification: review — code-review'
CM="git commit -am x -m '$TR'"
NONE="git commit -am x -m 'Verification: none — docs typo'"
BARE='git commit -am x'
edit() { printf '# %s\n' "$1" >> m.py; }

echo '=== A: off (the default) ==='
reset; set_repo_cfg -; edit a
row 'off: commit with no evidence passes' "$(commit s0 p1 "$BARE")" allow
# Run the hook with open / exists / listdir / makedirs watched: in off mode nothing under the state dir is touched
touched=$(python3 - "$FIX" "$W" "$HOOK" <<'PY'
import builtins, json, os, runpy, sys, io
fix, cwd, hook = sys.argv[1:]
sd = os.path.join(os.environ["CLAUDE_PLUGIN_DATA"], "commit-gate")
hits = []
def watch(f):
    def g(p, *a, **k):
        if str(p).startswith(sd):
            hits.append(str(p))
        return f(p, *a, **k)
    return g
builtins.open = watch(builtins.open)
os.path.exists = watch(os.path.exists); os.listdir = watch(os.listdir); os.makedirs = watch(os.makedirs)
for ev in (json.load(open(f"{fix}/upe-code-review.json")),
           {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git commit -am x"}}):
    ev.update(session_id="s0", prompt_id="p1", cwd=cwd)
    sys.stdin = io.StringIO(json.dumps(ev)); sys.argv = [hook]; sys.stdout = io.StringIO()
    try:
        runpy.run_path(hook, run_name="__main__")
    except SystemExit:
        pass
sys.stdout = sys.__stdout__
print(len(hits))
PY
)
row 'off: /code-review and git commit read no state (paths touched under the state dir)' "$([ "$touched" = 0 ] && echo none || echo "touched$touched")" none
row 'off: no state dir is created' "$([ -e "$CLAUDE_PLUGIN_DATA/commit-gate" ] && echo created || echo none)" none
row 'off: an unknown userConfig value counts as off' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=on commit s0 p1 "$BARE")" allow

for MODE in observe enforce; do
  export CLAUDE_PLUGIN_OPTION_COMMIT_GATE=$MODE
  if [ $MODE = observe ]; then NO=block; STALE=stale; else NO=deny; STALE=deny; fi
  echo "=== B: $MODE: evidence ==="
  reset; edit b1
  review s1 p1; stop s1 p1
  row "$MODE: fresh evidence (/code-review, pinned at Stop) + trailer passes" "$(commit s1 p2 "$CM")" allow
  row "$MODE: fresh evidence, no trailer" "$(commit s1 p2 "$BARE")" $NO
  row "$MODE: fresh evidence via the Skill tool + trailer passes" "$(reset; edit b1; skill s1b p1 code-review; stop s1b p1; commit s1b p2 "$CM")" allow
  row "$MODE: fresh evidence from another session on the same tree passes" "$(commit s1c p9 "$CM")" allow
  row "$MODE: same turn, before Stop (fix loop) + trailer passes" "$(reset; edit b2; review s2 p1; edit fix; commit s2 p1 "$CM")" allow
  reset; edit b3
  row "$MODE: missing evidence, no trailer" "$(commit s3 p1 "$BARE")" $NO
  row "$MODE: missing evidence, trailer claims a review that never ran" "$(commit s3b p1 "$CM")" $NO
  row "$MODE: missing evidence, explained (Verification: none — reason) passes" "$(commit s3c p1 "$NONE")" allow
  row "$MODE: missing evidence, none with an empty reason" "$(commit s3d p1 "git commit -am x -m 'Verification: none — '")" $NO
  reset; edit b4; review s4 p1; stop s4 p1; edit later
  row "$MODE: stale evidence (tree edited after the review) + trailer" "$(commit s4 p2 "$CM")" $STALE
  row "$MODE: stale evidence, no trailer" "$(commit s4 p2 "$BARE")" $STALE
  row "$MODE: interrupted turn (review never reached Stop), next turn" "$(reset; edit b5; review s5 p1; commit s5 p2 "$CM")" $STALE
  # No reset between these two: session A's review of an earlier tree is not "stale" evidence for session B
  reset; edit b6; review sA p1; stop sA p1; edit b6-later
  row "$MODE: another session's review of an earlier tree is not stale here (no trailer)" "$(commit sB p1 "$BARE")" $NO
  row "$MODE: another session's review of an earlier tree, trailer claims it" "$(commit sB2 p1 "$CM")" $NO
  row "$MODE: the session that ran it does see it as stale" "$(commit sA p2 "$CM")" $STALE
  echo "=== C: $MODE: two blocks, then the next commit passes ==="
  reset; edit c
  row "$MODE: block 1" "$(commit s6 p1 "$BARE")" $NO
  row "$MODE: block 2" "$(commit s6 p1 "$BARE")" $NO
  row "$MODE: third commit is released" "$(commit s6 p1 "$BARE")" release
  row "$MODE: counter reset: the next one is blocked again" "$(commit s6 p1 "$BARE")" $NO
  row "$MODE: the count is per session" "$(commit s6x p1 "$BARE")" $NO
done

echo '=== D: per-repo override on the default branch ==='
unset CLAUDE_PLUGIN_OPTION_COMMIT_GATE
reset; edit d
set_repo_cfg '{"commitGate": "enforce"}'
row 'userConfig off, default branch says enforce: blocked' "$(commit s7 p1 "$BARE")" deny
set_repo_cfg '{"commitGate": "observe"}'
row 'userConfig off, default branch says observe: would block' "$(commit s7b p1 "$BARE")" block
set_repo_cfg '{"commitGate": "off"}'
row 'userConfig enforce, default branch says off: passes' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=enforce commit s7c p1 "$BARE")" allow
set_repo_cfg '{"commitGate": "enforce", "verifiers": "^my-check$"}'
row 'default-branch verifiers: my-check counts' "$(reset; edit d2; skill s7d p1 my-check; stop s7d p1; commit s7d p2 "git commit -am x -m 'Verification: review — my-check'")" allow
row 'default-branch verifiers: code-review no longer counts' "$(reset; edit d3; review s7e p1; stop s7e p1; commit s7e p2 "$CM")" deny

echo '=== E: a branch cannot change the rule in its own working tree ==='
set_repo_cfg '{"commitGate": "enforce"}'
reset; edit e; mkdir -p .claude
printf '{"commitGate": "off"}\n' > .claude/verification.json
row 'working tree says off (uncommitted), default branch enforce: still blocked' "$(commit s8 p1 "$BARE")" deny
git checkout -qb feature; git add -A; git commit -qm 'turn it off on the branch'
row 'branch commits commitGate off: still blocked' "$(edit e2; commit s8b p1 "$BARE")" deny
printf '{"commitGate": "enforce", "verifiers": "^anything$"}\n' > .claude/verification.json
row 'working tree widens verifiers: its skill is not evidence' "$(skill s8c p1 anything; stop s8c p1; commit s8c p2 "git commit -am x -m 'Verification: review — anything'")" deny
git checkout -qf main && git clean -qfd && git branch -qD feature
set_repo_cfg -
reset; edit e3; mkdir -p .claude; printf '{"commitGate": "enforce"}\n' > .claude/verification.json
row 'userConfig observe, working tree says enforce: stays observe' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=observe commit s8d p1 "$BARE")" block
printf '{"commitGate": "off"}\n' > .claude/verification.json
row 'userConfig enforce, working tree says off: still enforced' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=enforce commit s8e p1 "$BARE")" deny

echo '=== F: reading the commit command (enforce) ==='
export CLAUDE_PLUGIN_OPTION_COMMIT_GATE=enforce
reset; edit f; review s9 p1; stop s9 p1
printf 'x\n\n%s\n' "$TR" > "$T/msg file.txt"
row 'trailer in -F <file>' "$(commit s9 p2 "git commit -a -F '$T/msg file.txt'")" allow
row 'trailer in -m "$(cat <<EOF ...)"' "$(commit s9 p2 "git commit -a -m \"\$(cat <<'EOF'
x

$TR
EOF
)\"")" allow
row 'trailer in -F - <<EOF' "$(commit s9 p2 "git commit -a -F - <<'EOF'
x

$TR
EOF")" allow
row 'trailer through --trailer' "$(commit s9 p2 "git commit -am x --trailer 'Verification: review — code-review'")" allow
row 'en dash and hyphen separators' "$(commit s9 p2 "git commit -am x -m 'Verification: review - code-review'")" allow
row 'message in a variable (cannot be read)' "$(commit s9 p2 'git commit -am "$MSG"')" deny
row 'git -C <dir with space> commit' "$(cd "$T" && commit s9 p2 "git -C '$W' commit -am x -m '$TR'")" allow
row 'after cd && git commit, no trailer' "$(commit s9 p2 "cd '$W' && git commit -am x")" deny
row 'not a commit: git commit-tree' "$(commit s9 p2 'git commit-tree HEAD^{tree} -m x')" allow
row 'not a commit: the words inside echo' "$(commit s9 p2 "echo 'git commit -am x'")" allow
row 'not a commit: --dry-run' "$(commit s9 p2 'git commit --dry-run -a')" allow
row 'an unlexable command (unbalanced quote) is logged as not checked' "$(commit s9 p2 'git commit -am "unterminated')" unparsed
row '-C <option-looking value> never reaches git log as an option' "$(r=$(commit s9 p2 "git commit -C '--output=$T/pwned'"); [ -e "$T/pwned" ] && echo written || echo "$r")" deny
git add -A; git commit -qm "x" -m "$TR"
row '--amend --no-edit keeps HEAD trailer' "$(commit s9 p2 'git commit --amend --no-edit')" allow
row 'subagent payload (agent_id, same session) is read like the main one' "$(ev pre-bash-subagent s9 p2 "tool_input={\"command\":$(j "git commit -am x")}" | grep -q '"deny"' && echo deny || echo allow)" deny

echo '=== G: origin default branch unknown, no origin ==='
reset; edit g
git remote set-head origin -d
row 'no local origin/HEAD: does not gate, says so' "$(commit s10 p1 "$BARE")" nogate
row 'no local origin/HEAD, userConfig off: silent' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s10 p1 "$BARE")" allow
git remote set-head origin main
N="$T/no origin"; git init -q -b main "$N"; ( in_dir "$N"; echo a > a; git add a; git commit -qm a; echo b >> a
  mkdir -p .claude; printf '{"commitGate": "enforce"}\n' > .claude/verification.json )
row 'no origin remote: the working tree file applies' "$(W="$N" CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s11 p1 "git commit -am x")" deny

echo '=== H: the log and report ==='
row 'report lists would-be blocks' "$(python3 "$HOOK" report | grep -q would_block && echo listed || echo missing)" listed
reset; edit h0; review s13 p1; stop s13 p1
git commit -qam x -m "$TR"; posted() { ev - s13 p2 'hook_event_name="PostToolUse"' 'tool_name="Bash"' "tool_input={\"command\":$(j "$1")}" "tool_response={\"stdout\":$(j "$2"),\"stderr\":\"\"}" >/dev/null; lastlog stamp; }
row 'after the commit: logged as committed with a backed stamp' "$(posted "$CM" "[main $(git rev-parse --short HEAD)] x")" backed
row 'the log line names the branch' "$(lastlog branch)" main
edit h1; git commit -qam y
row 'after a commit with no trailer: stamp missing' "$(posted "$BARE" "[main $(git rev-parse --short HEAD)] y")" missing
row 'the repo itself is untouched (no stray objects from the fingerprint)' "$(in_dir "$W"; before=$(git count-objects -v | sed -n 's/^count: //p'); review s12 p1; edit h; stop s12 p1; commit s12 p2 "$BARE" >/dev/null; [ "$(git count-objects -v | sed -n 's/^count: //p')" = "$before" ] && echo clean || echo wrote)" clean

rm -rf "$T"
