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
    unparsed) echo unparsed ;; unresolved) echo unresolved ;; allow|explained) echo allow ;; *) echo "other:$(lastlog decision)" ;;
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
  reset; edit b7; review sU p1; stop sU p1; printf 'new\n' > untracked-after-review.txt
  row "$MODE: an untracked file added after the review makes it stale" "$(commit sU p2 "$CM")" $STALE
  echo "=== C: $MODE: two blocks, then the next commit passes ==="
  reset; edit c
  row "$MODE: block 1" "$(commit s6 p1 "$BARE")" $NO
  row "$MODE: block 2" "$(commit s6 p1 "$BARE")" $NO
  row "$MODE: third commit is released" "$(commit s6 p1 "$BARE")" release
  row "$MODE: counter reset: the next one is blocked again" "$(commit s6 p1 "$BARE")" $NO
  row "$MODE: the count is per session" "$(commit s6x p1 "$BARE")" $NO
  reset; edit c2
  commit s21 p1 "$BARE" >/dev/null; review s21 p1; stop s21 p1
  row "$MODE: a passing commit after one block" "$(commit s21 p2 "$CM")" allow
  commit s21 p2 "$BARE" >/dev/null
  row "$MODE: an allow resets the count (second block after it is still a block)" "$(commit s21 p2 "$BARE")" $NO
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

set_repo_cfg '{"commitGate": true}'
row 'default branch has a non-string commitGate: userConfig enforce still applies' "$(reset; edit d4; CLAUDE_PLUGIN_OPTION_COMMIT_GATE=enforce commit s7f p1 "$BARE")" deny
row 'no error was logged for it' "$(grep -q '"decision": "error"' "$LOG" 2>/dev/null && echo logged || echo none)" none
row 'the unreadable repo value is logged as config_invalid' "$(grep -q '"decision": "config_invalid"' "$LOG" 2>/dev/null && echo logged || echo none)" logged
set_repo_cfg '{"commitGate": "bogus"}'
row 'default branch has a typo ("bogus"), userConfig unset: off (documented in Limitations)' "$(reset; edit d5; commit s7g p1 "$BARE")" allow

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
row 'git -C <dir with space> commit' "$(W0="$W"; W="$T" commit s9 p2 "git -C '$W0' commit -am x -m '$TR'")" allow
row 'a # inside a word does not hide the commit after it' "$(commit s9h p2 "git add docs/a#b.md && git commit -am x")" deny
row 'a commit inside a shell comment is not a commit' "$(commit s9c p2 'echo ok # then git commit -am x')" allow
row 'a # right after $(...) is part of the word: the commit after it is seen' "$(commit s9d p2 'echo $(true)# ; git commit -am x')" deny
row 'git commit -unormal (an option value with an a) is not -a' "$(reset; edit f3; git add m.py; review s9u p1; edit f3-fixed; stop s9u p1; commit s9u p2 "git commit -unormal -m x -m '$TR'")" deny
row 'bash -lc '"'"'git commit'"'"' (a -c cluster) is seen' "$(commit s9b p2 "bash -lc 'git commit -am x'")" deny
row 'git -C "$REPO" commit (a variable): noted and logged as unresolved, never denied' "$(commit s9v1 p2 'git -C "$REPO" commit -am x -m "'"$TR"'"')" unresolved
row 'cd "$REPO" && git commit: unresolved, not denied' "$(commit s9v2 p2 'cd "$REPO" && git commit -am x')" unresolved
row 'GIT_DIR=<repo>/.git git commit: unresolved, not denied' "$(commit s9v3 p2 "GIT_DIR='$W/.git' git commit -am x")" unresolved
row 'unresolved, the log says why' "$([ "$(lastlog why)" = "GIT_DIR / GIT_WORK_TREE" ] && echo named || echo missing)" named
row 'cd - && git commit: unresolved, not denied (cd - is not followed)' "$(commit s9v6 p2 'cd /tmp && cd - && git commit -am x')" unresolved
row 'unresolved three times in a row: still never denied' "$(commit s9v3 p2 'cd "$REPO" && git commit -am x' >/dev/null; commit s9v3 p2 'cd "$REPO" && git commit -am x' >/dev/null; commit s9v3 p2 'cd "$REPO" && git commit -am x')" unresolved
row 'cd "$(git rev-parse --show-toplevel)" && git commit: judged here (no trailer)' "$(commit s9t1 p2 'cd "$(git rev-parse --show-toplevel)" && git commit -am x' >/dev/null; lastlog decision | tr -d _)" wouldblock
row 'cd "$(git rev-parse --show-toplevel)" && git commit + trailer: passes' "$(commit s9t2 p2 'cd "$(git rev-parse --show-toplevel)" && git commit -am x -m "'"$TR"'"')" allow
row 'git -C "$(pwd)" commit: judged here (no trailer)' "$(commit s9t3 p2 'git -C "$(pwd)" commit -am x' >/dev/null; lastlog decision | tr -d _)" wouldblock
row 'git -C $(pwd) commit (unquoted) + trailer: passes' "$(commit s9t4 p2 'git -C $(pwd) commit -am x -m "'"$TR"'"')" allow
row 'git -C "$PWD" commit: judged here (no trailer)' "$(commit s9t5 p2 'git -C "$PWD" commit -am x' >/dev/null; lastlog decision | tr -d _)" wouldblock
row 'cd ${PWD} && git commit + trailer: passes' "$(commit s9t6 p2 'cd ${PWD} && git commit -am x -m "'"$TR"'"')" allow
row 'cd `pwd` && git commit: judged here (no trailer)' "$(commit s9t7 p2 'cd `pwd` && git commit -am x' >/dev/null; lastlog decision | tr -d _)" wouldblock
row 'sh -c -- '"'"'git commit'"'"' is seen' "$(commit s9b2 p2 "sh -c -- 'git commit -am x'")" deny
row 'git commit -S<keyid> -am x -m <trailer>: the key does not swallow the options' "$(commit s9k1 p2 "git commit -SDEADBEEFCAFE -am x -m '$TR'")" allow
row 'git commit -S<email>: same' "$(commit s9k2 p2 "git commit -Sci@example.com -am x -m '$TR'")" allow
row 'git commit -SABC -a -m <trailer>: passes' "$(commit s9k3 p2 "git commit -SABC -a -m '$TR'")" allow
row 'git --git-dir --work-tree from a dir that is not a repo: logged as unresolved, not blocked' "$(W0="$W"; W="$T" commit s9v4 p2 "git --git-dir='$W0/.git' --work-tree='$W0' commit -am x")" unresolved
row 'observe: cd "$REPO" && git commit is logged as unresolved, not blocked' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=observe commit s9v5 p2 'cd "$REPO" && git commit -am x')" unresolved
row 'after cd && git commit, no trailer' "$(commit s9 p2 "cd '$W' && git commit -am x")" deny
row 'not a commit: git commit-tree' "$(commit s9 p2 'git commit-tree HEAD^{tree} -m x')" allow
row 'not a commit: the words inside echo' "$(commit s9 p2 "echo 'git commit -am x'")" allow
row 'not a commit: --dry-run' "$(commit s9 p2 'git commit --dry-run -a')" allow
row 'an unlexable command (unbalanced quote) is logged as not checked' "$(commit s9 p2 'git commit -am "unterminated')" unparsed
row '-C <option-looking value> never reaches git log as an option' "$(r=$(commit s9 p2 "git commit -C '--output=$T/pwned'"); [ -e "$T/pwned" ] && echo written || echo "$r")" deny
reset; edit f2; git add m.py; review s9s p1; edit f2-fixed; stop s9s p1
row 'staged version differs from the verified working tree: blocked' "$(commit s9s p2 "git commit -m x -m '$TR'")" deny
row 'same, with -a (stages the verified version): passes' "$(commit s9s2 p2 "$CM")" allow
row 'same, naming the path (git commit <path> takes it from the working tree): passes' "$(commit s9s3 p2 "git commit -m x -m '$TR' m.py")" allow
row 'same, --only -- <path>: passes' "$(commit s9s4 p2 "git commit --only -m x -m '$TR' -- m.py")" allow
row 'same, -i <path> (stages that path): passes' "$(commit s9s5 p2 "git commit -i -m x -m '$TR' m.py")" allow
row 'same, -i <another path>: still blocked' "$(commit s9s6 p2 "git commit -i -m x -m '$TR' other.txt")" deny
row 'same, ... 2>&1 | tail -1 (a redirect is not a path): still blocked' "$(commit s9s7 p2 "git commit -m x -m '$TR' 2>&1 | tail -1")" deny
row 'same, ... > /dev/null: still blocked' "$(commit s9s8 p2 "git commit -m x -m '$TR' > /dev/null")" deny
row 'same, --pathspec-from-file (paths unknown): still blocked' "$(commit s9s9 p2 "git commit --pathspec-from-file=list.txt -m x -m '$TR'")" deny
row "same, -m '>x' (a message, not a redirection): still blocked" "$(commit s9s10 p2 "git commit --trailer '$TR' -m '>x' -m y")" deny
row 'same, > -a (a file named -a, not the option): still blocked' "$(commit s9s11 p2 "git commit -m x -m '$TR' > -a")" deny
row 'same, -- >/dev/null (a redirection after --, not a path): still blocked' "$(commit s9s12 p2 "git commit -m x -m '$TR' -- >/dev/null")" deny
row 'same, --mess x (an abbreviated --message; x is not a path): still blocked' "$(commit s9s13 p2 "git commit --trailer '$TR' --mess x")" deny
row "same, a quoted '>' before -i <path> (paths unknown): checked in full" "$(commit s9s14 p2 "git commit --trailer '$TR' -m x '>' -i m.py")" deny
reset; edit f; review s9 p1; stop s9 p1
git add -A; git commit -qm "x" -m "$TR"
row '--amend --no-edit keeps HEAD trailer' "$(commit s9 p2 'git commit --amend --no-edit')" allow
row 'subagent payload (agent_id, same session) is read like the main one' "$(ev pre-bash-subagent s9 p2 "tool_input={\"command\":$(j "git commit -am x")}" | grep -q '"deny"' && echo deny || echo allow)" deny

reset; git rm -q --cached m.py; review s9r p1; stop s9r p1
row 'git rm --cached <file> with the file still in the working tree (verified with it): blocked' "$(commit s9r p2 "git commit -m x -m '$TR'")" deny
git reset -q --hard; reset; git rm -q m.py; review s9r2 p1; stop s9r2 p1
row 'git rm <file> (gone from the working tree too): passes' "$(commit s9r2 p2 "git commit -m x -m '$TR'")" allow
git reset -q --hard
S="$T/subsrc"; git init -q -b main "$S"; ( in_dir "$S"; echo s > s; git add s; git commit -qm s )
reset; git -c protocol.file.allow=always submodule add -q "$S" sub 2>/dev/null; echo dirty >> sub/s
review s9m p1; stop s9m p1
row 'a staged submodule with a dirty worktree does not count as staged-then-edited' "$(commit s9m p2 "git commit -m x -m '$TR'")" allow
git reset -q --hard; git clean -qffd

echo '=== G: origin default branch unknown, no origin ==='
reset; edit g
git remote set-head origin -d
row 'no local origin/HEAD: does not gate, says so' "$(commit s10 p1 "$BARE")" nogate
row 'no local origin/HEAD, userConfig off: silent' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s10 p1 "$BARE")" allow
set_repo_cfg '{"commitGate": "enforce"}'; git remote set-head origin -d
row 'opt-in only in the repo file, origin/HEAD missing, before SessionStart: silent (cannot be read)' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s10b p1 "$BARE")" allow
row 'userConfig off, no repo file at HEAD or in the working tree: SessionStart does not ask origin' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off ev - s10b p1 'hook_event_name="SessionStart"' >/dev/null; git rev-parse -q --verify refs/remotes/origin/HEAD >/dev/null && echo asked || echo skipped)" skipped
mkdir -p .claude; printf '{"commitGate": "enforce"}\n' > .claude/verification.json
row 'the repo file in the working tree: SessionStart resolves origin/HEAD, then gated' "$(export CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off; ev - s10b p1 'hook_event_name="SessionStart"' >/dev/null; commit s10b p1 "$BARE")" deny
rm -f .claude/verification.json
SSHR="$T/ssh-repo"; git init -q -b main "$SSHR"; ( in_dir "$SSHR"; mkdir -p .claude; echo '{"commitGate": "observe"}' > .claude/verification.json
  git add .claude; git commit -qm cfg; git remote add origin ssh://nohost.invalid/r.git )
printf '#!/bin/sh\necho "$@" >> "%s"\nexit 1\n' "$T/ssh.args" > "$T/fakessh"; chmod +x "$T/fakessh"
row 'repo file at HEAD: SessionStart asks origin, ssh in BatchMode' "$(W="$SSHR" GIT_SSH_COMMAND="$T/fakessh" CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off ev - s10c p1 'hook_event_name="SessionStart"' >/dev/null; grep -q 'BatchMode=yes' "$T/ssh.args" 2>/dev/null && echo batch || { [ -s "$T/ssh.args" ] && echo prompting || echo none; })" batch
SSHR2="$T/ssh-repo2"; git clone -q "$SSHR" "$SSHR2"; git -C "$SSHR2" remote set-url origin ssh://nohost.invalid/r.git; git -C "$SSHR2" remote set-head origin -d
git -C "$SSHR2" config core.sshCommand "$T/fakessh2"; sed "s#ssh.args#ssh2.args#" "$T/fakessh" > "$T/fakessh2"; chmod +x "$T/fakessh2"
row 'core.sshCommand is kept (BatchMode added to it)' "$(W="$SSHR2" GIT_SSH_COMMAND= CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off ev - s10d p1 'hook_event_name="SessionStart"' >/dev/null; grep -q 'BatchMode=yes' "$T/ssh2.args" 2>/dev/null && echo kept || echo dropped)" kept
set_repo_cfg -
git remote set-head origin main
N="$T/no origin"; git init -q -b main "$N"; ( in_dir "$N"; echo a > a; git add a; git commit -qm a; echo b >> a
  mkdir -p .claude; printf '{"commitGate": "enforce"}\n' > .claude/verification.json )
row 'no origin remote: the working tree file applies' "$(W="$N" CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s11 p1 "git commit -am x")" deny

echo '=== I: where the commit runs (subshells, pushd / popd) ==='
OT="$T/other"; git init -q -b main "$OT"; ( in_dir "$OT"; echo o > o; git add o; git commit -qm o; echo p >> o )
set_repo_cfg '{"commitGate": "enforce"}'; reset; edit i
row '(cd <other> && true); git commit: the cd stays in the subshell, judged here' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14a p1 "(cd '$OT' && true); git commit -am x")" deny
row '( cd <other> ) && git commit: judged here' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14b p1 "( cd '$OT' ) && git commit -am x")" deny
row 'pushd <other> && popd && git commit: judged here' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14c p1 "pushd '$OT' >/dev/null && popd >/dev/null && git commit -am x")" deny
row '(cd <other> && git commit): judged there (ungated)' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14d p1 "(cd '$OT' && git commit -am x)")" allow
row 'mirror, from the ungated repo: (cd <gated> && true); git commit stays ungated' "$(W0="$W"; W="$OT" CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14e p1 "(cd '$W0' && true); git commit -am x")" allow
row 'mirror: pushd <gated> && popd && git commit stays ungated' "$(W0="$W"; W="$OT" CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14f p1 "pushd '$W0' >/dev/null && popd >/dev/null && git commit -am x")" allow
row 'env -C <other> git commit: judged there (ungated)' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14h p1 "env -C '$OT' git commit -am x")" allow
row 'mirror: env --chdir=<gated> git commit from the ungated repo: judged there' "$(W0="$W"; W="$OT" CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14i p1 "env --chdir='$W0' git commit -am x")" deny
row 'env -C "$VAR" git commit: unresolved' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14j p1 'env -C "$REPO" git commit -am x')" unresolved
row 'env -iC <dir> git commit (C inside a cluster): unresolved, not hidden' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14k p1 "env -iC '$OT' git commit -am x")" unresolved
row 'mirror: env --chd <gated> (an abbreviated --chdir) git commit from the ungated repo: judged there' "$(W0="$W"; W="$OT" CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14l p1 "env --chd '$W0' git commit -am x")" deny
row 'env -C <a> -C <b> git commit: unresolved' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14m p1 "env -C '$OT' -C '$W' git commit -am x")" unresolved
row 'popd with an empty stack: unresolved' "$(CLAUDE_PLUGIN_OPTION_COMMIT_GATE=off commit s14g p1 "popd && git commit -am x")" unresolved
set_repo_cfg -

echo '=== H: the log and report ==='
row 'report lists would-be blocks' "$(python3 "$HOOK" report | grep -q would_block && echo listed || echo missing)" listed
reset; edit h0; review s13 p1; stop s13 p1
# PreToolUse, then the real commit, then PostToolUse with what Bash printed
posted() { ev - s13 p2 'hook_event_name="PostToolUse"' 'tool_name="Bash"' "tool_input={\"command\":$(j "$1")}" "tool_response={\"stdout\":$(j "$2"),\"stderr\":\"\"}" 'duration_ms=2000' >/dev/null; lastlog decision; }
commit s13 p2 "$CM" >/dev/null; git commit -qam x -m "$TR"
row 'after the commit: logged as committed' "$(posted "$CM" "[main $(git rev-parse --short HEAD)] x")" committed
row 'its stamp is backed by the record' "$(lastlog stamp)" backed
row 'the log line names the branch' "$(lastlog branch)" main
row 'the next command (a push) does not log the same commit again as unseen' "$(n0=$(loglines); posted 'git push' '' >/dev/null; [ "$(loglines)" = "$n0" ] && echo once || echo twice)" once
edit h1; commit s13 p2 'git commit -qam y' >/dev/null; git commit -qam y
row 'git commit -q (no summary printed) is still logged' "$(posted 'git commit -qam y' '')" committed
row 'after a commit with no trailer: stamp missing' "$(lastlog stamp)" missing
edit h2; n0=$(loglines); commit s13 p2 'git commit -qam z' >/dev/null; posted 'git commit -qam z' '' >/dev/null
row 'a refused commit (HEAD did not move) is not logged as committed' "$(lastlog decision)" would_block
H2="$T/second"; git init -q -b main "$H2"; ( in_dir "$H2"; mkdir -p .claude; echo '{"commitGate": "observe"}' > .claude/verification.json; echo a > a; git add -A; git commit -qm a; echo b >> a )
edit h2b; C2="git -C '$W' commit -qam a5; git -C '$H2' commit -qam b5"
CLAUDE_PLUGIN_OPTION_COMMIT_GATE=observe commit s13 p2 "$C2" >/dev/null; git -C "$W" commit -qam a5; git -C "$H2" commit -qam b5
row 'two repos committed in one command: both logged' "$(n0=$(loglines); posted "$C2" '' >/dev/null; c=$(tail -n +$((n0 + 1)) "$LOG" | grep -c '"committed"'); [ "$c" = 2 ] && echo both || echo "only$c")" both
edit h3; git commit -qam w   # a commit the PreToolUse side never saw (as through make, eval, an alias)
row 'HEAD moved in a command not read as a commit: logged as committed' "$(n0=$(loglines); posted 'make release' ''; )" committed
row 'that line is marked unseen by the pre-commit check' "$([ "$(lastlog unseen)" = True ] && echo unseen || echo missing)" unseen
row 'a command that did not commit adds no line' "$(n0=$(loglines); posted 'ls -la' '' >/dev/null; [ "$(loglines)" = "$n0" ] && echo none || echo added)" none
edit h4; git commit -qam v
row 'a PostToolUse without duration_ms: no unseen line (no default window)' "$(n0=$(loglines); ev - s13 p2 'hook_event_name="PostToolUse"' 'tool_name="Bash"' 'tool_input={"command":"make release"}' 'tool_response={"stdout":"","stderr":""}' >/dev/null; [ "$(loglines)" = "$n0" ] && echo none || echo added)" none
row 'fingerprint changes on every same-size edit right after a commit (200 rounds, racy-clean index)' "$(in_dir "$W"; printf '\0\1A' > b.bin; git add b.bin; git commit -qm bin; python3 - "$HOOK" <<'PY'
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
import importlib.util
spec = importlib.util.spec_from_file_location("cg", sys.argv[1]); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
same = 0
for i in range(200):
    # Commit first, so the index is written in the same instant as the file (the racily clean case of git)
    with open("b.bin", "wb") as f: f.write(b"\0\1A" if i % 2 else b"\0\1C")
    subprocess.run(["git", "commit", "-qam", f"r{i}"], check=True)
    a = g.fingerprint(os.getcwd())
    with open("b.bin", "wb") as f: f.write(b"\0\1B")
    b = g.fingerprint(os.getcwd())
    same += a == b
print("changed" if same == 0 else f"same{same}")
PY
)" changed
row 'the repo itself is untouched (no stray objects from the fingerprint)' "$(in_dir "$W"; before=$(git count-objects -v | sed -n 's/^count: //p'); review s12 p1; edit h; stop s12 p1; commit s12 p2 "$BARE" >/dev/null; [ "$(git count-objects -v | sed -n 's/^count: //p')" = "$before" ] && echo clean || echo wrote)" clean

rm -rf "$T"
