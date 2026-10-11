#!/bin/bash
# Measure rm-guard (bash-guard.py's recursive rm guard).
set -u
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/bash-guard.py"
# A to K run with the worktree folder set to ~/.worktrees (setting worktree_dirs;
# Claude Code passes userConfig values to hooks as CLAUDE_PLUGIN_OPTION_<KEY>). L covers the empty setting
export CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/.worktrees'

probe() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]},
                      "cwd": os.environ.get("PROBE_CWD") or os.path.expanduser("~")})
p = subprocess.run(["python3", os.environ["HOOK"]],
                   input=payload, capture_output=True, text=True)
out = p.stdout.strip()
if not out:
    print("allow"); raise SystemExit
print(json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision", "allow"))
PY
}

row() { printf '  %-58s -> %-5s (expect %s)\n' "$2" "$(probe "$1")" "$3"; }

echo '=== A: the marker no longer works ==='
row "RM_GUARD_OK=1 rm -rf $HOME/somewhere" 'with RM_GUARD_OK=1 (absolute path)'    'deny'
row 'RM_GUARD_OK=1 rm -rf /'                       'with RM_GUARD_OK=1 (root)'       'deny'
row "SKIP=1 FORCE=1 rm -rf $HOME/somewhere" 'with other env var names'                'deny'

echo
echo '=== B: variable assignments in the same command are resolved (a real false positive) ==='
row 'T=/tmp/tclint-test; rm -rf $T; mkdir -p $T/x' 'assign /tmp in the same command (the real case)' 'allow'
row 'D=/tmp/a; rm -rf ${D}/sub'                    'the ${VAR}/sub form'                     'allow'
row 'W=~/.worktrees/foo; rm -rf $W'                'assign a worktree path (missing = undecidable worktree)' 'deny'

row 'T=/tmp/a; rm -rf $T'                          'assign /tmp (non-worktree is allowed via a variable)' 'allow'

echo
echo '=== C: unresolvable variables are denied as before (safe side) ==='
row 'rm -rf $UNKNOWN_VAR'                          'variable with no assignment'                      'deny'
row 'X=$(pwd); rm -rf $X'                          'command substitution on the right side (unresolvable)'       'deny'
row 'Y=/tmp/a; rm -rf $Z'                          'refers to a different variable'                    'deny'
row 'T=/tmp/a; T=$HOME/x; rm -rf $T'               'reassigned to an unresolvable value'              'deny'
row 'echo T=/tmp/a; rm -rf $T'                     'T=… inside an argument is not an assignment'       'deny'
row 'false && T=/tmp/a; rm -rf $T'                 'assignment that may not run'          'deny'
row 'rm -rf $T; T=/tmp/a'                          'assignment after the delete'                  'deny'

echo
echo '=== D: catastrophic targets are always denied (no regression) ==='
row 'H=/; rm -rf $H'                               'root via a variable'                  'deny'
row 'rm -rf ~'                                     'home'                              'deny'
row 'rm -rf /usr'                                  'system dir'                         'deny'
row 'rm -rf *'                                     'bare glob'                          'deny'

echo
echo '=== E: allowed as before (no regression) ==='
row 'rm -rf ./build'                               'relative path'                            'allow'
row 'rm -rf /tmp/foo'                              'literal /tmp'                     'allow'
row "rm -f $HOME/x"                              'non-recursive rm'                       'allow'
row "ls -la $HOME"                               'not even rm'                       'allow'

echo
echo '=== F: trash (move to Trash) can be undone, so it passes outside safe areas too ==='
row "trash $HOME/.claude/state/example-tool"   'trash outside safe areas'                  'allow'
row 'trash ~/Documents/old.txt'                    'trash a file under home'        'allow'
row 'trash ~'                                      'home itself'                      'deny'
row 'trash /usr'                                   'system dir'                         'deny'
row 'trash *'                                      'bare glob'                          'deny'
row 'trash ~/.worktrees/no-such-wt'                 'trash an undecidable worktree'        'deny'

echo
echo '=== G: heredoc bodies and quoted text are data (not evaluated as commands) ==='
row $'cat > /tmp/x.md <<\'EOF\'\nrm -rf ~/.claude/state/foo\nEOF' 'delete command text in a heredoc body'   'allow'
row $'gh issue create --body "Steps:\nrm -rf ~/.claude/state/foo"' 'delete command text inside quotes'   'allow'
row $'cat > /tmp/x.md <<EOF\nok\nEOF\nrm -rf ~/.claude/state/foo' 'a real delete after a heredoc'   'deny'

echo
echo '=== H: a squash-merged worktree (SHA differs from main) can be deleted when the PR head matches ==='
# Point HOME at a temp dir and create a worktree under ~/.worktrees whose branch is 1 commit ahead of main.
# Fake gh to switch between "there is / is no MERGED PR with this head" (no network access)
T0=${TMPDIR:-/tmp}; FH=$(mktemp -d "${T0%/}/wtguard-home.XXXX")   # drop the trailing / (a // in $HOME would judge differently from the real environment)
git -C "$FH" init -q -b main repo && git -C "$FH/repo" commit -q --allow-empty -m base
git -C "$FH/repo" worktree add -q -b feat/sq "$FH/.worktrees/sq"
git -C "$FH/.worktrees/sq" commit -q --allow-empty -m work
SQ_HEAD=$(git -C "$FH/.worktrees/sq" rev-parse HEAD)
mkdir -p "$FH/bin-merged" "$FH/bin-other"
printf '#!/bin/bash\necho %s\n' "$SQ_HEAD" > "$FH/bin-merged/gh"
printf '#!/bin/bash\necho 0000000000000000000000000000000000000000\n' > "$FH/bin-other/gh"
chmod +x "$FH/bin-merged/gh" "$FH/bin-other/gh"
HOME="$FH" PATH="$FH/bin-merged:$PATH" row 'git worktree remove ~/.worktrees/sq' 'MERGED PR head matches HEAD'      'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH"  row 'git worktree remove ~/.worktrees/sq' 'MERGED PR head differs (extra commits)' 'deny'
: > "$FH/.worktrees/sq/dirty.txt"
HOME="$FH" PATH="$FH/bin-merged:$PATH" row 'git worktree remove ~/.worktrees/sq' 'head matches but there are uncommitted files'  'deny'

echo
echo '=== I: deletes inside wrappers, subshells, command substitutions and find get the same verdict ==='
row 'sudo rm -rf /'                                'via sudo'                           'deny'
row 'env rm -rf ~'                                 'via env'                            'deny'
row 'command rm -rf ~'                             'via command'                        'deny'
row 'nohup rm -rf ~ &'                             'via nohup'                          'deny'
row "bash -c 'rm -rf ~'"                           'bash -c string'                    'deny'
row 'sh -c "rm -rf ~"'                             'sh -c string'                      'deny'
row "eval 'rm -rf ~'"                              'eval string'                       'deny'
row 'echo ~ | xargs rm -rf'                        'via xargs (arguments from stdin)'         'deny'
row 'find ~ -delete'                               'find -delete'                        'deny'
row 'find ~ -name x -exec rm {} +'                 'find -exec rm'                       'deny'
row '(rm -rf ~)'                                   'subshell'                          'deny'
row 'echo $(rm -rf ~)'                             'command substitution $( )'                    'deny'
row 'echo `rm -rf ~`'                              'command substitution (backquotes)'        'deny'
row 'echo "$(rm -rf ~)"'                           'command substitution inside double quotes'        'deny'
row 'sudo rm -rf /tmp/x'                           '/tmp is allowed even via sudo'          'allow'
row "bash -c 'rm -rf ./build'"                     'relative path is allowed even in bash -c'         'allow'
row "find . -name '*.pyc' -delete"                 'find -delete from the current dir'          'allow'
row 'find /tmp/x -exec rm {} +'                    'find -exec rm from /tmp'            'allow'
row 'echo "(rm -rf ~)"'                            'parentheses inside quotes are data'               'allow'
row 'sudo --user root rm -rf /'                    'sudo long option taking a value'        'deny'
row 'sudo -nu root rm -rf /'                       'sudo short-option bundle'            'deny'
row 'env -iu FOO rm -rf ~'                         'env short-option bundle'             'deny'
row 'timeout --signal KILL 5 rm -rf ~'             'timeout long option taking a value'     'deny'
row 'find -delete'                                 'find -delete without a start path'        'deny'
row 'find . -delete'                               'unfiltered find -delete from the current dir'   'deny'
row 'find -L . -mindepth 1 -delete'                'find -delete with only global options'     'deny'
row "find -name '*.pyc' -delete"                   'no start path but filtered: allow'    'allow'
row 'find /tmp -maxdepth 0 -exec rm -rf ~/data ;'   'another path inside find -exec rm'            'deny'
row "find . -name x -exec sh -c 'rm -rf ~' ;"       'delete inside find -exec sh -c'           'deny'
# worktree-guard scans inside the start path, so use a small folder instead of home (large on CI)
SMALL=$(mktemp -d "${TMPDIR:-/tmp}/rmguard-small.XXXX")
PROBE_CWD="$SMALL" row "find . -type d -name build -exec rm -rf {} +"  'find -exec rm {} is judged by the start path'     'allow'
rm -rf "$SMALL"
row "X=/tmp/a; bash -c 'rm -rf \$X/*'"                'child shell does not see unexported variables' 'deny'
row "export X=/tmp/a; bash -c 'rm -rf \$X/x'"         'exported but not decided statically (safe side)'   'deny'
row 'if false; then T=/tmp/a; fi; rm -rf $T'        'assignment inside if may not run'     'deny'
row 'T=; rm -rf ${T:-/}'                            'variable expansion with an operator'                  'deny'
row 'T=/tmp/a; rm -rf ${T}/x'                       'the ${VAR} form resolves as before'           'allow'

echo
echo '=== J: the worktree delete marker works only at the start of the delete command; relative paths are resolved ==='
# Continues from H: sq has an uncommitted file, so it counts as unmerged
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'WORKTREE_RM_OK=1 git worktree remove ~/.worktrees/sq' 'marker at the start of the delete command'          'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'WORKTREE_RM_OK=1 trash ~/.worktrees/sq'               'marker at the start of trash'               'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'echo WORKTREE_RM_OK=1; git worktree remove ~/.worktrees/sq' 'marker as an echo argument'        'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'git worktree remove ~/.worktrees/sq # WORKTREE_RM_OK=1' 'marker in a comment'              'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'WORKTREE_RM_OK=1 true; git worktree remove ~/.worktrees/sq' 'marker at the start of another command'   'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'git -C ~/repo worktree remove ~/.worktrees/sq'       'worktree remove with git -C'          'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'cd ~/.worktrees && rm -rf sq'                        'cd then rm -rf a relative path'           'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" PROBE_CWD="$FH/.worktrees" row 'rm -rf sq'                'cwd is ~/.worktrees, rm -rf a relative path'  'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'rm -rf ~/.worktrees'                                 '~/.worktrees itself'                  'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'sudo trash ~/.worktrees/sq'                          'trash via sudo'                      'deny'
HOME="$FH" PATH="$FH/bin-other:$PATH" row 'cd ~/.worktrees/sq && rm -rf build'                  'cleaning a subdirectory inside a worktree'    'allow'
HOME="$FH" PATH="$FH/bin-other:$PATH" PROBE_CWD="$FH/.worktrees/sq" row 'rm -rf node_modules'  'cwd inside a worktree, rm -rf a relative path'  'allow'
echo
echo '=== K: worktrees outside ~/.worktrees (<repo>/.claude/worktrees etc.) get the same verdict ==='
# feat is unmerged, 1 commit ahead of main; done equals main and is clean
git -C "$FH/repo" worktree add -q -b feat/cc "$FH/repo/.claude/worktrees/feat"
git -C "$FH/repo/.claude/worktrees/feat" commit -q --allow-empty -m work
git -C "$FH/repo" worktree add -q -b done/cc "$FH/repo/.claude/worktrees/done"
mkdir -p "$FH/repo/.claude/worktrees/feat/build" "$FH/repo/build"
K() { HOME="$FH" PATH="$FH/bin-other:$PATH" PROBE_CWD="${KCWD:-$FH/repo}" row "$@"; }
K 'rm -rf .claude/worktrees/feat'                 'rm -rf an unmerged worktree by relative path'   'deny'
K "rm -rf $FH/repo/.claude/worktrees/feat"        'rm -rf an unmerged worktree by absolute path'   'deny'
K 'trash .claude/worktrees/feat'                  'trash an unmerged worktree'             'deny'
K 'find .claude/worktrees/feat -delete'           'find -delete an unmerged worktree'      'deny'
K 'rm -rf .claude/worktrees'                      'the whole folder containing an unmerged worktree'     'deny'
K 'rm -rf .claude'                                'a folder further up'                    'deny'
K 'WORKTREE_RM_OK=1 rm -rf .claude/worktrees/feat' 'marker at the start of the delete command'           'allow'
K 'rm -rf .claude/worktrees/done'                 'merged, clean worktree'          'allow'
K 'git worktree remove .claude/worktrees/done'    'git worktree remove a merged one'        'allow'
K 'rm -rf .claude/worktrees/feat/build'           'cleaning a subdirectory inside a worktree'      'allow'
KCWD="$FH/repo/.claude/worktrees/feat" K 'rm -rf build' 'cwd inside a worktree, rm -rf a relative path' 'allow'
K 'rm -rf build'                                  'folder with no worktree'              'allow'
K 'rm -rf .claude/worktrees/*'                    'glob including an unmerged worktree'        'deny'
K 'rm -rf .claude/worktrees/f*'                   'glob prefix match on an unmerged worktree'     'deny'
K 'rm -rf .claude/worktrees/d*'                   'glob matches only the merged worktree' 'allow'
# Worktrees kept together in a folder that is not under git
git -C "$FH/repo" worktree add -q -b feat/ext "$FH/ext/feat"
git -C "$FH/ext/feat" commit -q --allow-empty -m work
K "rm -rf $FH/ext"                                'parent folder not under git (absolute path)' 'deny'
KCWD="$FH" K 'rm -rf ext'                         'parent folder not under git (relative path)' 'deny'
K 'rm -rf .claude/{worktrees,cache}'              'brace expansion including an unmerged worktree'  'deny'
K 'rm -rf .claude/{cache,tmp}'                    'brace expansion hits no worktree'      'allow'
K "find . -name '*.pyc' -delete"                  'filtered find -delete (cleanup)'          'allow'
K 'find . -name feat -exec rm -rf {} +'           '-exec rm is blocked even when filtered'          'deny'
# An unmerged worktree of one repo inside an unrelated repo
git -C "$FH" init -q -b main outer && git -C "$FH/outer" commit -q --allow-empty -m base
git -C "$FH/repo" worktree add -q -b feat/nested "$FH/outer/bucket/feat"
git -C "$FH/outer/bucket/feat" commit -q --allow-empty -m work
KCWD="$FH/outer" K 'rm -rf bucket'                'unmerged worktree inside another repo'    'deny'
# Shell options change what a glob matches (dotglob, nocaseglob, extglob), so check whatever could match
git -C "$FH/repo" worktree add -q -b feat/hidden "$FH/outer/hb/.hidden/feat"
git -C "$FH/outer/hb/.hidden/feat" commit -q --allow-empty -m work
KCWD="$FH/outer" K 'shopt -s dotglob; rm -rf hb/*' 'dotglob matches a folder starting with .'     'deny'
KCWD="$FH/outer" K 'shopt -s nocaseglob; rm -rf B*' 'nocaseglob matches ignoring case' 'deny'
KCWD="$FH/outer" K 'shopt -s extglob; rm -rf @(bucket|x)' 'matches with extglob'                 'deny'
# Also catch deep worktrees (no depth cutoff)
git -C "$FH/repo" worktree add -q -b feat/deep "$FH/deep/a/b/c/d/e/feat"
git -C "$FH/deep/a/b/c/d/e/feat" commit -q --allow-empty -m work
K "rm -rf $FH/deep"                               'unmerged worktree 6 levels down'          'deny'
# globstar `**` descends any number of levels, so look below the folder before `**`
KCWD="$FH" K 'shopt -s globstar; rm -rf deep/**/feat' 'globstar ** reaches a deep worktree'      'deny'
KCWD="$FH" K 'rm -rf wide/**/x'                   'no worktree in the folder before **'     'allow'
# If cut off at the folder-count limit, we can't say there is no worktree where we didn't look, so block
# (use relative paths so rm-guard doesn't block on macOS, where the temp area isn't /tmp)
mkdir -p "$FH/wide/1" "$FH/wide/2" "$FH/wide/3" "$FH/wide/4"
KCWD="$FH" GUARDS_SCAN_LIMIT=3 K 'rm -rf wide'    'scan cut off at the limit (undecidable)'      'deny'
KCWD="$FH" K 'rm -rf wide'                        'confirmed no worktree within the limit'    'allow'
KCWD="$FH" GUARDS_SCAN_LIMIT=3 K 'rm -rf wide/*'  'limit counted overall, not per glob match'   'deny'
KCWD="$FH" K 'rm -rf wide/*'                      'glob matches checked within the limit'         'allow'
# Can't check inside an unreadable folder (skipped on CI running as root, where it is readable)
if [ "$(id -u)" != 0 ]; then
  mkdir -p "$FH/locked/in" && chmod 000 "$FH/locked/in"
  KCWD="$FH" K 'sudo rm -rf locked'               'contains an unreadable folder (undecidable)'        'deny'
  chmod 755 "$FH/locked/in"
fi
KCWD="$FH" GUARDS_SCAN_LIMIT=3 K "find wide -name x -exec rm -rf {} +" 'filtered find -exec rm is blocked if the scan is incomplete' 'deny'
K 'rm -rf .claude/worktrees/x{1..1000000000}'      'huge range: no hang, blocked as undecidable'  'deny'
# find -L and -H follow symlinks (rm removes only the link itself)
ln -s "$FH/ext" "$FH/alias"
mkdir -p "$FH/lk" && ln -s "$FH/ext" "$FH/lk/in"
KCWD="$FH" K 'find -L alias -name feat -exec rm -rf {} +' 'find -L follows a start-path link'     'deny'
KCWD="$FH" K 'find -H alias -name feat -exec rm -rf {} +' 'find -H follows a start-path link'     'deny'
KCWD="$FH" K 'find alias -name feat -exec rm -rf {} +'    'find that does not follow links'            'allow'
KCWD="$FH" K 'find -L lk -name feat -exec rm -rf {} +'    'find -L follows links inside'           'deny'
KCWD="$FH" K 'find lk -follow -name feat -exec rm -rf {} +' '-follow also follows links inside'       'deny'
KCWD="$FH" K 'find -H lk -name feat -exec rm -rf {} +'    'find -H does not follow links inside'   'allow'
KCWD="$FH" K 'rm -rf alias'                               'rm removes only the link itself'          'allow'
# Range brace expansion, the expansion-count limit, quoted glob characters
K 'rm -rf .claude/worktrees/{done,fea{s..u}}'      'range brace expansion hits an unmerged worktree'   'deny'
K "rm -rf .claude/{$(printf 'x%s,' $(seq 1 300))worktrees}" 'brace expansion over the limit (undecidable)' 'deny'
mkdir -p "$FH/repo/bk"
git -C "$FH/repo" worktree add -q -b feat/bk "$FH/repo/bk/b[1]"
git -C "$FH/repo/bk/b[1]" commit -q --allow-empty -m work
K "rm -rf 'bk/b[1]'"                               'quoted [ ] is a literal path'     'deny'
git -C "$FH/repo" worktree add -q -b feat/bk2 "$FH/repo/bk/{done,feat}"
git -C "$FH/repo/bk/{done,feat}" commit -q --allow-empty -m work
K "rm -rf 'bk/{done,feat}'"                        'quoted { } is a literal path'     'deny'
# A worktree under $TMPDIR (rm-guard treats $TMPDIR as safe)
git -C "$FH/repo" worktree add -q -b feat/tmp "$FH/tmpd/feat"
git -C "$FH/repo/../tmpd/feat" commit -q --allow-empty -m work
TMPDIR="$FH/tmpd" K 'rm -rf "$TMPDIR/feat"'        'unmerged worktree under $TMPDIR'         'deny'
TMPDIR="$FH/tmpd" K 'rm -rf ${TMPDIR:-/tmp}/feat'  'also the ${TMPDIR:-…} form'                    'deny'
TMPDIR="$FH/tmpd" K 'rm -rf "$TMPDIR/other"'       'non-worktree path under $TMPDIR'        'allow'
# Even if the hook inherits another worktree's GIT_DIR, judge by the target's repo
GIT_DIR="$FH/repo/.git/worktrees/done" GIT_WORK_TREE="$FH/repo/.claude/worktrees/done" \
  K 'rm -rf .claude/worktrees/feat'               'even with GIT_DIR pointing to another worktree'    'deny'

echo
echo '=== L: which guard blocks, by the worktree_dirs setting (empty = default, or set) ==='
# rm-guard lets the temp area (/tmp) through, so use a nonexistent HOME (outside the temp area) here.
# Output is allow / wtguard (blocked by worktree-guard) / rmguard (blocked by rm-guard)
who() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}, "cwd": "/"})
out = subprocess.run(["python3", os.environ["HOOK"]], input=payload, capture_output=True, text=True).stdout.strip()
if not out:
    print("allow"); raise SystemExit
r = json.loads(out).get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
print("wtguard" if "worktree-guard" in r else "rmguard" if "rm-guard" in r else "other")
PY
}
lrow() { printf '  %-58s -> %-7s (expect %s)\n' "$2" "$(who "$1")" "$3"; }
NH=/nonexistent-guards-home
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS= HOME=$NH lrow 'rm -rf ~/.worktrees/x'      'empty: ~/.worktrees is not special'          'rmguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS= HOME=$NH lrow 'W=~/.worktrees/x; rm -rf $W' 'empty: same via a variable'                        'rmguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/.worktrees' HOME=$NH lrow 'rm -rf ~/.worktrees/x' '~/.worktrees: blocked as an undecidable worktree' 'wtguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/wt, ~/.worktrees' HOME=$NH lrow 'rm -rf ~/wt/x'       'first of a comma-separated list'      'wtguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~/wt, ~/.worktrees' HOME=$NH lrow 'rm -rf ~/.worktrees/x' 'second of a comma-separated list'    'wtguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='/' HOME=$NH lrow 'rm -rf /opt/x'               'root is not accepted as a location'            'rmguard'
CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS='~' HOME=$NH lrow 'rm -rf ~/x'                  'home is not accepted as a location either'            'rmguard'

echo
echo '=== M: rm-guard passes the root of a merged, clean worktree wherever it lives ==='
# Drop the temp-area handling and look only at rm-guard's classification (K's feat is unmerged, done is merged and clean)
classify() {
  CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS= HOME="$FH" PATH="$FH/bin-other:$PATH" python3 - "$1" <<'PY'
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("bash_guard", os.environ["HOOK"])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.SAFE_PREFIXES = ()
print(m._classify_target(sys.argv[1]))
PY
}
crow() { printf '  %-58s -> %-5s (expect %s)\n' "$2" "$(classify "$1")" "$3"; }
crow "$FH/repo/.claude/worktrees/done"            'root of a merged, clean worktree'   'safe'
crow "$FH/repo/.claude/worktrees/feat"            'root of an unmerged worktree'               'other'
crow "$FH/repo/.claude/worktrees/done/build"      'path that is not a worktree root'               'other'
crow "$FH/repo"                                   'the main working tree'                        'other'

rm -rf "$FH"
