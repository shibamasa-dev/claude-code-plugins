#!/bin/bash
# Live check of the acceptance criteria of knowledge-freshness.py.
# Builds a fixture tree under a fake HOME and runs the real hook, so the real ~/.claude is untouched.
set -u
HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/knowledge-freshness.py"
H=$(mktemp -d "${TMPDIR:-/tmp}/kf-fixture.XXXX")
F="$H/.claude"
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

# resolve the real interpreter first: a pyenv/xcrun shim misbehaves under the fake HOME and writes to stderr
PY=$(python3 -c 'import sys; print(sys.executable)' 2>/dev/null || echo python3)
run() { echo '{"hook_event_name":"SessionStart"}' | HOME="$H" CLAUDE_PLUGIN_OPTION_FRESHNESS_TARGETS="${TARGETS:-}" "$PY" "$HOOK" 2>"$H/err"; echo "|exit=$?"; }

echo '=== case 1: expired, unset and broken mixed ==='
OUT=$(run)
CODE=${OUT##*|}
BODY=${OUT%|*}
[ "$CODE" = exit=0 ] && r=ok || r=ng; echo "  $CODE -> $r (expect ok: exit=0, never BLOCK)"
E=$(wc -c <"$H/err" | tr -d ' ')
[ "$E" = 0 ] && r=ok || r=ng; echo "  stderr ${E}B -> $r (expect ok: 0B)"
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
CODE2=${OUT2##*|}
[ "$CODE2" = exit=0 ] && r=ok || r=ng; echo "  $CODE2 -> $r (expect ok: exit=0)"
P=$(( ${#OUT2} - ${#CODE2} - 1 ))
[ "$P" = 0 ] && r=ok || r=ng; echo "  payload ${P}B -> $r (expect ok: 0B)"

echo
echo '=== case 3: does not crash when the directories are gone ==='
rm -rf "$F/rules" "$F/reference" "$F/skills"
OUT3=$(run)
CODE3=${OUT3##*|}
[ "$CODE3" = exit=0 ] && r=ok || r=ng; echo "  $CODE3 -> $r (expect ok: exit=0)"


echo
echo '=== case 4: custom freshness_targets (a dir outside ~/.claude, with a ~ entry too) ==='
mkdir -p "$H/custom/sub" "$F/rules"
printf -- '---\nlast_reviewed: 2026-01-01\nreview_after: 2026-08-01\n---\n# stale\n' > "$H/custom/sub/SKILL.md"
printf -- '---\nlast_reviewed: 2026-01-01\nreview_after: 2026-08-01\n---\n# stale default dir\n' > "$F/rules/old.md"
TARGETS="$H/custom:*/SKILL.md"
OUT4=$(run); CODE4=${OUT4##*|}; BODY4=${OUT4%|*}
[ "$CODE4" = exit=0 ] && r=ok || r=ng; echo "  $CODE4 -> $r (expect ok: exit=0)"
case "$BODY4" in *"custom/sub/SKILL.md"*) r=ok;; *) r=ng;; esac; echo "  warns about the custom file -> $r"
case "$BODY4" in *"rules/old.md"*) r=ng;; *) r=ok;; esac; echo "  default dirs not scanned when overridden -> $r"
TARGETS="~/.claude/rules:*.md"
OUT5=$(run)
case "$OUT5" in *"~/.claude/rules/old.md"*|*"rules/old.md"*) r=ok;; *) r=ng;; esac; echo "  '~' in a target is expanded -> $r"
mkdir -p "$H/deep/a/b"
printf -- '---\nlast_reviewed: 2026-01-01\nreview_after: 2026-08-01\n---\n# deep\n' > "$H/deep/a/b/x.md"
TARGETS="$H/deep:**/*.md"
OUT8=$(run)
case "$OUT8" in *"deep/a/b/x.md"*) r=ok;; *) r=ng;; esac; echo "  '**' reaches a file two levels deep -> $r"
TARGETS=""
OUT6=$(run)
case "$OUT6" in *"rules/old.md"*) r=ok;; *) r=ng;; esac; echo "  empty value falls back to the default targets -> $r"
TARGETS="garbage-without-colon"
OUT7=$(run); [ "${OUT7##*|}" = exit=0 ] && r=ok || r=ng; echo "  malformed value still exits 0 -> $r"

rm -rf "$H"
