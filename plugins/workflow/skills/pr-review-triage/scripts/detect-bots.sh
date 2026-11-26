#!/bin/bash
# Prints the repo's review settings (tools to use for heavy and light PRs, and whether the tools' automatic review is ON).
# Usage: detect-bots.sh [--light | --auto] [--regex]   (run inside the repo's working tree)
#   (no args): ids of the tools to use for heavy PRs, one per line (an id is a file name in references/tools/<id>.md)
#   --light: what to use for light PRs. `claude` (Claude reviews; the default) and tool ids, one per line (either one, or both)
#   --auto:  whether the tools' automatic review is ON. `on` / `off` (default off)
#   --regex: instead of ids, print one line with a regex of author logins (full match) to pass to jq's test() (for the Monitor filter)
# How it decides (the first one found, from the top; the result is not saved):
#   1. A line in the repo's CLAUDE.md / AGENTS.md / .claude/CLAUDE.md on the default branch (origin/<default>; the working tree only
#      when there is no origin remote; exit 4 when origin's default branch cannot be told) (`review-heavy:` / `review-light:` / `review-auto:`; `review-heavy: none` means "no tools").
#      A line added or changed by a PR takes effect once it is merged and the local origin/<default> is fetched
#   2. Environment variables CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY / _LIGHT / _AUTO (userConfig `review_heavy` / `review_light` / `review_auto`)
#   3. Defaults: light is `claude`, auto is `off`. heavy has no default (exit 4)
# Does not guess from bots that showed up on past PRs. With automatic review turned off, light PRs leave no bot trace, so the guess would be empty.
# exit: 0 = decided (prints nothing for "no tools") / 4 = no heavy line and no setting, or origin's default branch unknown / 5 = written but unreadable
#       (not a single known id, or auto is neither on nor off) (on 4 or 5 the caller asks the user)
set -u
KEY=heavy; REGEX=0
for a in "$@"; do
  case "$a" in
    --light) KEY=light ;;
    --auto) KEY=auto ;;
    --regex) REGEX=1 ;;
  esac
done
# id=author login (full match, bot accounts only). When adding one, update references/tools/<id>.md as well.
# A partial match would leave room to pick up a human account's post (e.g. codex-fan) as a bot review and follow its instructions
BOTS='coderabbit=coderabbitai\[bot\] codex=chatgpt-codex-connector\[bot\] copilot=Copilot|copilot-pull-request-reviewer\[bot\] gemini=gemini-code-assist\[bot\] cursor-bugbot=cursor\[bot\]'

# Git variables that select a repository are dropped, so the repo of the current directory is read, not one named by the environment
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY
root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
# Read the files from the default branch (origin/<default>), not the working tree, so a PR cannot pick the tools that review it.
# The name is the local origin/HEAD, used without the network while origin named it and the ref it names has not moved since
# (detect-bots-origin-head in the git common dir holds "<name> <sha>"). Otherwise origin is asked (ls-remote, no prompt): after a
# fetch moved that ref (a branch pushed under the old default's name after a rename), on the first run, or when origin/HEAD is
# missing or dangles; a success rewrites the local origin/HEAD. A failed network attempt is remembered for an hour (the mtime of
# detect-bots-origin-miss in the git common dir); then, and within that hour, the local answer is kept (a stale one is fine). origin/main or origin/master
# is never guessed: when the default branch cannot be told, exit 4 (the caller asks).
# A missing origin/<name> is fetched once into that ref (explicit, so a single-branch clone gets it too).
# Without an origin remote no PR exists, so the working tree is read.
net() {  # net <git args...>: a network git command, no prompt, killed after 5 s together with its children (an ssh child
         # holding the output pipe would otherwise keep $(...) waiting); a failure is remembered
  GIT_TERMINAL_PROMPT=0 perl -e '$p = fork; defined $p or exit 1; unless ($p) { setpgrp(0, 0); exec @ARGV or exit 127 }
    $SIG{ALRM} = sub { kill "KILL", -$p; exit 1 }; alarm 5; waitpid $p, 0; $rc = $?; kill "KILL", -$p;
    exit($rc & 127 ? 1 : $rc >> 8)' git -C "$root" "$@" </dev/null 2>/dev/null || { : >> "$miss"; touch "$miss"; return 1; }
}
show() {  # show <rev:path>: the blob's text; a blob missing from a partial clone is fetched only through net, not within the hour
  o=$(git -C "$root" rev-parse --verify --quiet "$1" 2>/dev/null) || return 1
  # Local only when rev-list prints the oid itself: "?<oid>" (missing), or an error with no output (git before 2.46 rejects
  # a missing tip), both mean "not local". It never fetches
  if [ "$(git -C "$root" rev-list --objects --missing=print "$o" 2>/dev/null)" = "$o" ]; then
    git -C "$root" show "$1" 2>/dev/null
  else
    [ "$net_ok" = 1 ] && net show "$1"
  fi
}
ref=
if git -C "$root" remote get-url origin >/dev/null 2>&1; then
  common=$(git -C "$root" rev-parse --path-format=absolute --git-common-dir)
  miss="$common/detect-bots-origin-miss"; head="$common/detect-bots-origin-head"
  net_ok=1; [ -n "$(find "$miss" -mmin -60 2>/dev/null)" ] && net_ok=0
  # Without --short: a tag or branch named origin/<name> would make the short form ambiguous (remotes/origin/<name>)
  name=$(git -C "$root" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null)
  case $name in refs/remotes/origin/?*) name=${name#refs/remotes/origin/} ;; *) name= ;; esac
  # A dangling origin/HEAD (its ref was pruned) is not fetched by name: that name may now be any pushed branch
  [ -n "$name" ] && ! git -C "$root" rev-parse --verify --quiet "refs/remotes/origin/$name" >/dev/null && name=
  stamp() { printf '%s %s' "$1" "$(git -C "$root" rev-parse --verify --quiet "refs/remotes/origin/$1" 2>/dev/null)"; }
  asked=
  if { [ -z "$name" ] || [ "$(cat "$head" 2>/dev/null)" != "$(stamp "$name")" ]; } && [ "$net_ok" = 1 ]; then
    asked=$(net ls-remote --symref origin HEAD | sed -n 's|^ref: refs/heads/\([^[:space:]]*\)[[:space:]]*HEAD$|\1|p')
    if [ -n "$asked" ]; then
      name=$asked
      git -C "$root" symbolic-ref refs/remotes/origin/HEAD "refs/remotes/origin/$name" 2>/dev/null
    else
      : >> "$miss"; touch "$miss"; net_ok=0
    fi
  fi
  if [ -z "$name" ]; then
    echo "detect-bots: cannot tell origin's default branch (no local origin/HEAD, origin unreachable; retried after 1 hour)" >&2
    exit 4
  fi
  ref=refs/remotes/origin/$name
  git -C "$root" rev-parse --verify --quiet "$ref" >/dev/null || [ "$net_ok" = 0 ] \
    || net fetch --quiet origin -- "+refs/heads/$name:$ref" >/dev/null
  if git -C "$root" rev-parse --verify --quiet "$ref" >/dev/null; then
    [ -n "$asked" ] && { stamp "$name"; echo; } > "$head" 2>/dev/null
  else
    echo "detect-bots: cannot read origin/$name; skipping the repo's review-* lines" >&2
  fi
else
  echo "detect-bots: no origin remote: reading the review-* lines from the working tree" >&2
fi
line=
for f in CLAUDE.md AGENTS.md .claude/CLAUDE.md; do
  if [ -n "$ref" ]; then
    if ! text=$(show "$ref:$f"); then
      # Absent on the default branch: try the next file. Present but unreadable: skip the repo's lines (never a later file)
      listed=$(git -C "$root" ls-tree --name-only "$ref" -- "$f" </dev/null 2>/dev/null) && [ -z "$listed" ] && continue
      echo "detect-bots: cannot read $f on ${ref#refs/remotes/}; skipping the repo's review-* lines" >&2
      line=; break
    fi
  else
    [ -f "$root/$f" ] || continue
    text=$(cat "$root/$f")
  fi
  line=$(printf '%s\n' "$text" | grep -i -m1 -E "^[-* ]*review-$KEY:" || true)
  [ -n "$line" ] && break
done

case $KEY in
  heavy) env=${CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY:-} ;;
  light) env=${CLAUDE_PLUGIN_OPTION_REVIEW_LIGHT:-} ;;
  auto) env=${CLAUDE_PLUGIN_OPTION_REVIEW_AUTO:-} ;;
esac
if [ -n "$line" ]; then
  raw=${line#*:}
elif [ -n "$env" ]; then
  raw=$env
elif [ "$KEY" = light ]; then
  raw=claude
elif [ "$KEY" = auto ]; then
  raw=off
else
  echo "detect-bots: no review-heavy: line and no userConfig review_heavy (not guessing)" >&2
  exit 4
fi
norm=$(printf '%s\n' "$raw" | tr ',' '\n' | tr -d ' `' | tr 'A-Z' 'a-z' | grep -v -x '')

if [ "$KEY" = auto ]; then
  case "$norm" in
    on|off) echo "$norm"; exit 0 ;;
    *) echo "detect-bots: review-auto must be on or off (cannot read '$(printf '%s' "$norm" | paste -sd, -)')" >&2; exit 5 ;;
  esac
fi
# For light, `claude` is not a tool (Claude does the review), so print it first, separately from tool ids.
# When listed together with tools (e.g. claude, codex) it means "Claude reviews and also waits for the listed tools' results". Not included in --regex
CLAUDE=0
if [ "$KEY" = light ] && printf '%s\n' "$norm" | grep -qx claude; then
  CLAUDE=1
  norm=$(printf '%s\n' "$norm" | grep -v -x claude)
  if [ -z "$norm" ]; then
    [ "$REGEX" = 1 ] || echo claude
    exit 0
  fi
fi

# Drop ids not in the table (macOS bash 3.2 misparses a case inside $( ), so it lives in a function)
known() {
  while read -r id; do
    case " $BOTS" in
      *" $id="*) echo "$id" ;;
      *) echo "detect-bots: dropping unknown tool '$id' (not in references/tools/)" >&2 ;;
    esac
  done
}
asked=$(printf '%s\n' "$norm" | grep -v -x none)
ids=$(printf '%s\n' "$asked" | grep -v -x '' | known)
# Something other than none was written but no known id is left (a typo, etc.): do not treat it like "no tools" with exit 0
if [ -n "$asked" ] && [ -z "$ids" ]; then
  echo "detect-bots: not a single known id (to use no tools, write review-$KEY: none)" >&2
  exit 5
fi

if [ "$REGEX" = 1 ]; then
  # Make it a full-match regex (^(...)$) so it does not become a partial match when passed to jq's test()
  re=$(for b in $BOTS; do printf '%s\n' "$ids" | grep -qx "${b%%=*}" && printf '%s\n' "${b#*=}"; done | paste -sd'|' -)
  [ -n "$re" ] && printf '^(%s)$\n' "$re"
else
  [ "$CLAUDE" = 1 ] && echo claude
  [ -n "$ids" ] && printf '%s\n' "$ids"
fi
exit 0
