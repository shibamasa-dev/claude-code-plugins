#!/bin/bash
# Prints the repo's review settings (tools to use for heavy and light PRs, and whether the tools' automatic review is ON).
# Usage: detect-bots.sh [--light | --auto] [--regex]   (run inside the repo's working tree)
#   (no args): ids of the tools to use for heavy PRs, one per line (an id is a file name in references/tools/<id>.md)
#   --light: what to use for light PRs. `claude` (Claude reviews; the default) and tool ids, one per line (either one, or both)
#   --auto:  whether the tools' automatic review is ON. `on` / `off` (default off)
#   --regex: instead of ids, print one line with a regex of author logins (full match) to pass to jq's test() (for the Monitor filter)
# How it decides (the first one found, from the top; the result is not saved):
#   1. A line in the repo's CLAUDE.md / AGENTS.md / .claude/CLAUDE.md (`review-heavy:` / `review-light:` / `review-auto:`; `review-heavy: none` means "no tools")
#   2. Environment variables CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY / _LIGHT / _AUTO (userConfig `review_heavy` / `review_light` / `review_auto`)
#   3. Defaults: light is `claude`, auto is `off`. heavy has no default (exit 4)
# Does not guess from bots that showed up on past PRs. With automatic review turned off, light PRs leave no bot trace, so the guess would be empty.
# exit: 0 = decided (prints nothing for "no tools") / 4 = no heavy line and no setting / 5 = written but unreadable
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

root=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
line=
for f in CLAUDE.md AGENTS.md .claude/CLAUDE.md; do
  [ -f "$root/$f" ] || continue
  line=$(grep -i -m1 -E "^[-* ]*review-$KEY:" "$root/$f" || true)
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
