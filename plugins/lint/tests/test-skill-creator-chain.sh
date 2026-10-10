#!/bin/bash
# skill-creator-chain.py の実測。Skill の PostToolUse で、skill-creator のときだけ skill-lint の案内を注入するか。
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/skill-creator-chain.py"

# injected <skill 名>: 出力に skill-lint の additionalContext があれば yes、出力が空なら none、それ以外は other
injected() {
  out=$(printf '{"hook_event_name":"PostToolUse","session_id":"s","tool_name":"Skill","tool_input":{"skill":"%s"}}' "$1" | python3 "$HOOK")
  case "$out" in
    *additionalContext*skill-lint*) echo yes ;;
    '') echo none ;;
    *) echo other ;;
  esac
}
row() { printf '  %-58s -> %-5s (%s 期待)\n' "$1" "$2" "$3"; }

echo '=== skill-creator への連鎖 ==='
row 'skill-creator なら注入する' "$(injected skill-creator)" 'yes'
row '名前空間付きの skill-creator でも注入する' "$(injected skill-creator:skill-creator)" 'yes'
expansion() { out=$(printf '{"hook_event_name":"UserPromptExpansion","session_id":"s"}' | python3 "$HOOK" --expansion); case "$out" in *skill-lint*) echo yes ;; *) echo no ;; esac; }
row '/skill-creator の直接入力（--expansion）でも案内を出す' "$(expansion)" 'yes'
row 'ほかのスキルなら何も出さない' "$(injected issue-ops)" 'none'
