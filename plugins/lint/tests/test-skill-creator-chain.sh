#!/bin/bash
# Measures skill-creator-chain.py: on the Skill PostToolUse, does it inject the skill-lint hint only for skill-creator?
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/skill-creator-chain.py"

# injected <skill name>: yes if the output has the skill-lint additionalContext, none if the output is empty, other otherwise
injected() {
  out=$(printf '{"hook_event_name":"PostToolUse","session_id":"s","tool_name":"Skill","tool_input":{"skill":"%s"}}' "$1" | python3 "$HOOK")
  case "$out" in
    *additionalContext*skill-lint*) echo yes ;;
    '') echo none ;;
    *) echo other ;;
  esac
}
row() { printf '  %-58s -> %-5s (expect %s)\n' "$1" "$2" "$3"; }

echo '=== chaining to skill-creator ==='
row 'injects for skill-creator' "$(injected skill-creator)" 'yes'
row 'injects for namespaced skill-creator too' "$(injected skill-creator:skill-creator)" 'yes'
expansion() { out=$(printf '{"hook_event_name":"UserPromptExpansion","session_id":"s"}' | python3 "$HOOK" --expansion); case "$out" in *skill-lint*) echo yes ;; *) echo no ;; esac; }
row 'prints the hint when /skill-creator is typed (--expansion)' "$(expansion)" 'yes'
row 'prints nothing for other skills' "$(injected issue-ops)" 'none'
