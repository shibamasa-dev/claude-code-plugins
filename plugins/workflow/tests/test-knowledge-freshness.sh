#!/bin/bash
# Live check of the acceptance criteria of knowledge-freshness.py.
# Builds a fixture tree and runs a copy with ROOT swapped, so the real ~/.claude is untouched.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/knowledge-freshness.py"
F=/tmp/kf-fixture
rm -rf "$F"
mkdir -p "$F/rules" "$F/reference" "$F/skills/alpha" "$F/skills/beta"

# expired (in the past)
printf -- '---\npaths:\n  - "**/*.md"\nlast_reviewed: 2026-01-01\nreview_after: 2026-08-01\n---\n\n# expired\n' \
  > "$F/rules/expired.md"
# not yet due (in the future)
printf -- '---\nlast_reviewed: 2026-09-01\nreview_after: 2027-03-01\n---\n\n# fresh\n' \
  > "$F/rules/fresh.md"
# no frontmatter at all
printf -- '# freshness not set\nbody only.\n' > "$F/reference/no-frontmatter.md"
# frontmatter without last_reviewed
printf -- '---\nname: beta\ndescription: x\n---\n\n# missing key\n' > "$F/skills/beta/SKILL.md"
# broken YAML
printf -- '---\nname: alpha\nlast_reviewed: "broken value\nreview_after: ????\n---\n\n# broken\n' \
  > "$F/skills/alpha/SKILL.md"

# make a copy with only ROOT swapped
sed "s|os.path.expanduser(\"~/.claude\")|\"$F\"|" "$HOOK" > "$F/hook.py"

run() { echo '{"hook_event_name":"SessionStart"}' | python3 "$F/hook.py" 2>"$F/err"; echo "|exit=$?"; }

echo '=== case 1: expired, unset and broken mixed ==='
OUT=$(run)
CODE=${OUT##*|}
BODY=${OUT%|*}
echo "  $CODE  (expect exit=0: never BLOCK)"
echo "  stderr: $(wc -c <"$F/err" | tr -d ' ')B (expect 0)"
python3 - "$BODY" <<'PY'
import json, sys
d = json.loads(sys.argv[1])
ctx = d["hookSpecificOutput"]["additionalContext"]
print("  --- injected context ---")
for line in ctx.splitlines():
    print("   ", line)
PY

echo
echo '=== case 2: completely silent when everything is fresh ==='
rm -f "$F/rules/expired.md" "$F/reference/no-frontmatter.md" "$F/skills/beta/SKILL.md" "$F/skills/alpha/SKILL.md"
rmdir "$F/skills/alpha" "$F/skills/beta" 2>/dev/null
OUT2=$(run)
echo "  ${OUT2##*|}  (expect exit=0)"
echo "  stdout: ${#OUT2} chars, payload $(( ${#OUT2} - ${#CODE} - 1 ))B (expect 0)"

echo
echo '=== case 3: does not crash when the directories are gone ==='
rm -rf "$F/rules" "$F/reference" "$F/skills"
OUT3=$(run)
echo "  ${OUT3##*|}  (expect exit=0)"

rm -rf "$F"
