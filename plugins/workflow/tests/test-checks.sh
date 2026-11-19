#!/bin/bash
# Live check of the local-checks test at PR creation (hooks/checks.py, asked by dev_flow_gate.py) against a throwaway
# origin (bare repo) and a clone of it, in a path with a space and non-ASCII characters.
# The hook's CLAUDE_PLUGIN_DATA and HOME point at the temp directory, so real state is untouched (no network access:
# the clone's origin URL is rewritten to a GitHub-shaped one that is never contacted; fetches name the bare repo).
# `checks.py run` is started with another CLAUDE_PLUGIN_DATA, as it is from Bash in a real session.
# DEV_FLOW_GATE_HOOK=<path> runs the rows against another copy of the hooks directory's dev_flow_gate.py
# (used to show each row fails without its logic).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="${DEV_FLOW_GATE_HOOK:-$HERE/../hooks/dev_flow_gate.py}"
CHECKS="$(dirname "$HOOK")/checks.py"
T=$(mktemp -d "${TMPDIR:-/tmp}/pc.XXXX")
# Guard: every git write below happens under $T (an empty or unexpected path would commit into the caller's repo)
case "$T" in ""|/) echo "mktemp failed" >&2; exit 1 ;; esac
[ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
export CLAUDE_PLUGIN_DATA="$T/data" HOME="$T" GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
unset CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE CLAUDE_PLUGIN_OPTION_COMMIT_GATE GH_REPO GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
O="$T/origin.git"; SEED="$T/seed"; W="$T/作業 リポ"; WT="$T/wt 二"

# A git that counts its calls (for the off row) and can be told to fail `add -A` (the fingerprint then is unavailable)
REAL_GIT="$(command -v git)"; mkdir -p "$T/bin"
cat > "$T/bin/git" <<EOF
#!/bin/bash
[ -n "\${GIT_CALLS:-}" ] && echo x >> "\$GIT_CALLS"
if [ -n "\${FAIL_ADD:-}" ]; then for a in "\$@"; do [ "\$a" = add ] && exit 1; done; fi
exec "$REAL_GIT" "\$@"
EOF
chmod +x "$T/bin/git"

in_dir() {  # in_dir <dir>: cd there and confirm that git sees exactly that directory as the top level
  cd "$1" || exit 1
  [ "$(git rev-parse --show-toplevel)" = "$(pwd -P)" ] || { echo "not at the top of $1 (pwd=$(pwd))" >&2; exit 1; }
}
git init -q --bare -b main "$O"
git clone -q "$O" "$SEED" 2>/dev/null; in_dir "$SEED"
printf 'def add(a, b):\n    return a + b\n' > m.py; git add m.py; git commit -qm init; git push -q origin main
git clone -q "$O" "$W"; in_dir "$W"
git remote set-url origin https://github.com/O/R.git   # never contacted; makes the repo "O/R" for the connector rows
git checkout -q -b feat
COMMON="$(git rev-parse --path-format=absolute --git-common-dir)"
PASSES="$COMMON/workflow-pr-checks.json"

# set_repo_cfg <json|-> : put .claude/verification.json on origin's main (- removes it), then bring it into the clone
set_repo_cfg() {
  ( in_dir "$SEED"; mkdir -p .claude
    if [ "$1" = - ]; then git rm -q --ignore-unmatch .claude/verification.json; else printf '%s\n' "$1" > .claude/verification.json; git add .claude; fi
    git commit -qm cfg --allow-empty; git push -q origin main )
  git -C "$W" fetch -q "$O" '+refs/heads/*:refs/remotes/origin/*'
}
reset() { rm -rf "$CLAUDE_PLUGIN_DATA" "$PASSES" "$PASSES.lock"; in_dir "$W"; git checkout -q -- . ; git clean -qfd; }
edit() { printf '# %s\n' "$1" >> "$W/m.py"; }
# run_checks [args] : `checks.py run` as Bash starts it (another plugin's data directory in the environment)
# Prints the exit code as a word (run-all.sh reads a verdict as lowercase letters): zero / one / two / three
word() { case "$1" in 0) echo zero ;; 1) echo one ;; 2) echo two ;; 3) echo three ;; *) echo "n$1" ;; esac; }
run_checks() { ( cd "$W" && CLAUDE_PLUGIN_DATA="$T/another-plugin" python3 "$CHECKS" run "$@" >/dev/null 2>&1; word $? ); }

j() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }
LOG="$CLAUDE_PLUGIN_DATA/checks/log.jsonl"
loglines() { [ -f "$LOG" ] && wc -l < "$LOG" | tr -d ' ' || echo 0; }
lastlog() { tail -1 "$LOG" | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get(sys.argv[1])).lower())' "$1"; }
# verdict <hook output> <log lines before> -> deny (the hook's JSON) or, from the decision it logged:
# block (would_block in observe) / pass / explained / release / nogate / nocommand / unresolved / unchecked;
# quiet when nothing was logged
verdict() {
  case "$1" in *'"permissionDecision": "deny"'*'[dev-flow-gate]'*) echo bodydeny; return ;;
               *'"permissionDecision": "deny"'*) echo deny; return ;; esac
  [ "$(loglines)" = "$2" ] && { echo quiet; return; }
  case "$(lastlog decision)" in
    would_block) echo block ;; allow) echo pass ;; released) echo release ;; *) lastlog decision ;;
  esac
}
OK_BODY=$'Summary\n\nRefs #5\nArch-Review: not-needed \xe2\x80\x94 tests only'
# create <session> [bash command] : PreToolUse for a Bash `gh pr create` in the clone (default: body passed with --body)
create() {
  n0=$(loglines); cmd="${2:-gh pr create --title t --body '$OK_BODY'}"
  out=$(printf '{"hook_event_name":"PreToolUse","session_id":"%s","cwd":%s,"tool_name":"Bash","tool_input":{"command":%s}}' \
    "$1" "$(j "$W")" "$(j "$cmd")" | PATH="$T/bin:$PATH" python3 "$HOOK")
  printf '%s' "$out" > "$T/last_out"; verdict "$out" "$n0"
}
said() { grep -q -- "$1" "$T/last_out" && echo yes || echo no; }   # whether the last `create` output has the text
# conn <session> <owner> <repo> <head> [body] : PreToolUse for the connector's create_pull_request
conn() {
  n0=$(loglines)
  out=$(printf '{"hook_event_name":"PreToolUse","session_id":"%s","cwd":%s,"tool_name":"mcp__github__create_pull_request","tool_input":{"owner":"%s","repo":"%s","title":"t","head":"%s","base":"main","body":%s}}' \
    "$1" "$(j "$W")" "$2" "$3" "$4" "$(j "${5:-$OK_BODY}")" | python3 "$HOOK")
  verdict "$out" "$n0"
}
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }

echo '=== A: off (the default) does nothing ==='
reset
row 'no config anywhere: gh pr create' "$(create a1)" quiet
row 'no config anywhere: connector' "$(conn a1 O R feat)" quiet
# The working tree asks for enforce, the default branch has no file, userConfig is unset: still off
mkdir -p "$W/.claude"; printf '{"prChecksGate":"enforce","prChecks":"false"}\n' > "$W/.claude/verification.json"
export GIT_CALLS="$T/gitcalls"; : > "$GIT_CALLS"
row 'working tree says enforce, default branch has no file: gh pr create' "$(create a2)" quiet
n=$(wc -l < "$GIT_CALLS" | tr -d ' '); unset GIT_CALLS
row 'off: the hook prints nothing' "$( [ -s "$T/last_out" ] && echo output || echo empty)" empty
row 'off: at most 6 local git calls for a PR creation (2 are dev-flow-gate own)' "$( [ "$n" -le 6 ] && echo bounded || echo "many:$n")" bounded
row 'off: no state, log or pass file is created' "$( [ -e "$CLAUDE_PLUGIN_DATA/checks" ] || [ -e "$PASSES" ] && echo wrote || echo nothing)" nothing
row 'off: the body check still denies a body without markers' "$(create a3 "gh pr create --title t --body 'no markers'")" bodydeny
set_repo_cfg '{"prChecksGate":"off","prChecks":"test -f m.py"}'
CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE=enforce; export CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE
row 'repo file says off, userConfig says enforce: the repo file wins' "$(create a4)" quiet
unset CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE

echo '=== B: observe logs and never blocks ==='
reset; set_repo_cfg '{"prChecksGate":"observe","prChecks":"test -f m.py"}'
edit one
row 'no recorded pass' "$(create b1)" block
row 'observe says so in a note (additionalContext), not a denial' "$(said additionalContext)" yes
row 'the log line has had_pass false' "$(lastlog had_pass)" false
row 'the log line has the head commit' "$( [ "$(lastlog pr_head)" = "$(git -C "$W" rev-parse HEAD)" ] && echo head || echo other)" head
row 'the log line marks uncommitted changes' "$(lastlog dirty)" true
row 'checks.py run: the command passes' "$(run_checks)" zero
row 'the pass is in the git common dir, not in the plugin data of the caller' "$( [ -f "$PASSES" ] && [ ! -e "$T/another-plugin" ] && echo common || echo elsewhere)" common
row 'recorded pass for this tree' "$(create b1)" pass
row 'the log line has had_pass true' "$(lastlog had_pass)" true
edit two
row 'an edit after the pass' "$(create b1)" block
row 'report lists the would-be blocks' "$(word "$(python3 "$CHECKS" report | grep -c would_block | tr -d ' ')")" two

echo '=== C: enforce ==='
reset; set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f m.py"}'
edit one
row 'no recorded pass: gh pr create' "$(create c1)" deny
row 'no recorded pass: connector' "$(conn c2 O R feat)" deny
create c3 >/dev/null
row 'the denial names the runner to start' "$(said 'checks.py run')" yes
# The command the denial names must run as written, also when the plugin lives under a path with a space
mkdir -p "$T/plug in"; cp "$(dirname "$HOOK")"/*.py "$T/plug in/"
( HOOK="$T/plug in/dev_flow_gate.py"; create c3b >/dev/null )
RUNNER=$(python3 -c 'import json,re,sys; r=json.load(open(sys.argv[1]))["hookSpecificOutput"]["permissionDecisionReason"]; print(re.search(r"Run `(python3 .*? run)`", r).group(1))' "$T/last_out")
row 'the runner in the denial runs as written from a plugin path with a space' "$( (cd "$W" && sh -c "$RUNNER" >/dev/null 2>&1; word $?) )" zero
row 'recorded pass: gh pr create' "$(create c4)" pass
row 'recorded pass: connector' "$(conn c5 O R feat)" pass
row 'recorded pass: gh pr create --body-file - with a heredoc' "$(create c6 "gh pr create --title t --body-file - <<'EOF'
$OK_BODY
EOF")" pass
row 'the body check comes first' "$(create c7 "gh pr create --title t --body 'no markers'")" bodydeny
edit two
row 'an edit after the pass' "$(create c8)" deny
row 'Local-Checks: none with a reason in the body' "$(create c9 "gh pr create --title t --body '$OK_BODY
Local-Checks: none — docs only'")" explained
row 'Local-Checks: none with no reason' "$(create c10 "gh pr create --title t --body '$OK_BODY
Local-Checks: none —
next line'")" deny
row 'Local-Checks: none inside an HTML comment does not count' "$(create c10b "gh pr create --title t --body '$OK_BODY
<!-- Local-Checks: none — template text -->'")" deny
row 'two denials in a session, then the third is let through' "$(create c11 >/dev/null; create c11 >/dev/null; create c11)" release
row 'after a release the count starts again' "$(create c11)" deny

create c12 >/dev/null; create c12 >/dev/null; run_checks >/dev/null; create c12 >/dev/null; edit three
row 'a creation that passed resets the count (two denials, a pass, then an edit)' "$(create c12)" deny

echo '=== D: what records a pass ==='
reset; set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f nope.py"}'
row 'checks.py run: a failing command exits non-zero' "$(run_checks)" one
row 'a failing command records nothing' "$(create d1)" deny
set_repo_cfg '{"prChecksGate":"enforce","prChecks":"echo x > gen.txt"}'
row 'checks.py run: a command that changes the tree exits 3' "$(run_checks)" three
row 'a run that changed the tree records nothing' "$(create d2)" deny
reset; set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f nope.py"}'
# The branch rewrites the command it is judged by: `run` still runs the default branch's command
mkdir -p "$W/.claude"; printf '{"prChecksGate":"off","prChecks":"true"}\n' > "$W/.claude/verification.json"
row 'checks.py run ignores the working tree command' "$(run_checks)" one
row 'the working tree cannot switch the gate off' "$(create d3)" deny
row 'checks.py run --working-tree runs the working tree command' "$(run_checks --working-tree)" zero
row '--working-tree records nothing' "$(create d4)" deny
reset; set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f m.py"}'
edit one; run_checks >/dev/null
set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f m.py && true"}'
row 'a pass under the previous command does not count' "$(create d5)" deny
reset; set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f m.py"}'
edit one; git -C "$W" commit -qam change; run_checks >/dev/null
git -C "$W" worktree add -q -b feat2 "$WT" feat
row 'another worktree with the same change shares the pass' "$(create d6 "cd '$WT' && gh pr create --title t --body '$OK_BODY'")" pass
git -C "$W" worktree remove --force "$WT"; git -C "$W" branch -qD feat2; git -C "$W" reset -q --hard origin/main

echo '=== E: not certain, so never denied (enforce) ==='
reset; set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f m.py"}'
edit one
row 'cd to a variable' "$(create e1 "cd \"\$DIR\" && gh pr create --title t --body '$OK_BODY'")" unresolved
row 'gh -R names another repo' "$(create e2 "gh pr create -R other/repo --title t --body '$OK_BODY'")" unresolved
row 'gh -R names this repo' "$(create e3 "gh pr create -R O/R --title t --body '$OK_BODY'")" deny
row 'gh --head names another branch' "$(create e4 "gh pr create --head other --title t --body '$OK_BODY'")" unresolved
row 'gh --head names this branch in origin (owner:branch)' "$(create e5 "gh pr create --head O:feat --title t --body '$OK_BODY'")" deny
row 'gh --head names the same branch name in another owner fork' "$(create e5b "gh pr create --head me:feat --title t --body '$OK_BODY'")" unresolved
row 'connector: another repo' "$(conn e6 O other feat)" unresolved
row 'connector: another head' "$(conn e7 O R other)" unresolved
row 'connector: the same branch name in another owner fork' "$(conn e7b O R me:feat)" unresolved
row 'detached HEAD' "$(git -C "$W" checkout -q --detach; create e8; git -C "$W" checkout -q feat)" unresolved
row 'the fingerprint is unavailable' "$(FAIL_ADD=1 create e9)" unchecked
git -C "$W" symbolic-ref -d refs/remotes/origin/HEAD
CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE=enforce; export CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE
row 'origin default branch unknown (userConfig enforce)' "$(create e10)" nogate
row 'checks.py run with the default branch unknown exits 2' "$(run_checks)" two
unset CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE
row 'origin default branch unknown (userConfig off)' "$(create e11)" quiet
git -C "$W" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
set_repo_cfg '{"prChecksGate":"enforce"}'
row 'gate on with no prChecks command' "$(create e12)" nocommand
row 'checks.py run with no command exits 2' "$(run_checks)" two
set_repo_cfg '{"prChecksGate":"enforce","prChecks":"test -f m.py"'   # not JSON
row 'config on the default branch is not JSON (userConfig unset)' "$(create e13)" quiet
CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE=enforce; export CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE
row 'config on the default branch is not JSON (userConfig enforce)' "$(create e14)" nocommand
set_repo_cfg '{"prChecksGate":true,"prChecks":"test -f m.py"}'
row 'prChecksGate is not a mode: userConfig is used' "$(create e15)" deny
row 'and the invalid value is logged' "$(word "$(grep -c config_invalid "$LOG" | tr -d ' ')")" one
unset CLAUDE_PLUGIN_OPTION_PR_CHECKS_GATE


echo '=== F: no origin remote, and a long command ==='
SOLO="$T/solo"; git init -q -b main "$SOLO"; ( in_dir "$SOLO"; printf 'x\n' > a.txt; mkdir .claude
  printf '{"prChecksGate":"enforce","prChecks":"test -f a.txt"}\n' > .claude/verification.json; git add -A; git commit -qm init )
row 'no origin remote: the working tree file is read' "$(create f1 "cd '$SOLO' && gh pr create --title t --body '$OK_BODY'")" deny
LONG="test -f m.py$(printf ' && true%.0s' $(seq 1 80))"
reset; set_repo_cfg "{\"prChecksGate\":\"enforce\",\"prChecks\":\"$LONG\"}"
row 'a command over 400 characters is denied too' "$(create f2)" deny
row 'and the denial does not show a cut-off prefix of it' "$(said 'true && true')" no

rm -rf "$T"
