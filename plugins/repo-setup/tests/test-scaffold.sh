#!/bin/bash
# Measures remote-setup's scaffold.py in a temp repo. Expected values come from the skill text (SKILL.md, "Generate the scaffold"
# table and "Local safety check") and the script's docstring: setup.sh is always overwritten, steps.sh and environment-setup.sh
# are kept, the SessionStart hook is merged without duplicates, the generated setup.sh stays silent locally.
set -u
SCAFFOLD="$(cd "$(dirname "$0")/.." && pwd)/skills/remote-setup/scripts/scaffold.py"
TMP=$(mktemp -d) || exit 1; trap 'rm -rf "$TMP"' EXIT
row() {  # row <description> <got> <want>: the verdict is ok when got equals want (run-all.sh reads lowercase words after ->)
  if [ "$2" = "$3" ]; then printf '  %-62s -> ok (expect ok)\n' "$1"; else printf '  %s [got: %s, want: %s] -> bad (expect ok)\n' "$1" "$2" "$3"; fi
}
yn() { if "$@" >/dev/null 2>&1; then echo yes; else echo no; fi; }
# hooks <settings.json>: how many SessionStart entries mention remote-setup/setup.sh
hooks() { python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); print(sum("remote-setup/setup.sh" in h.get("command","") for e in s["hooks"]["SessionStart"] for h in e["hooks"]))' "$1"; }

R="$TMP/fresh"; mkdir "$R"
python3 "$SCAFFOLD" "$R" >/dev/null; rc=$?
D="$R/scripts/remote-setup"
echo '=== fresh repo ==='
row 'exit status' "$([ $rc = 0 ] && echo ok || echo bad)" 'ok'
row 'creates setup.sh' "$(yn test -f "$D/setup.sh")" 'yes'
row 'creates steps.sh' "$(yn test -f "$D/steps.sh")" 'yes'
row 'creates environment-setup.sh' "$(yn test -f "$D/environment-setup.sh")" 'yes'
row 'the three scripts are executable' "$(yn test -x "$D/setup.sh" -a -x "$D/steps.sh" -a -x "$D/environment-setup.sh")" 'yes'
row 'the three scripts pass bash -n' "$(yn bash -c 'for f in "$0"/*.sh; do bash -n "$f" || exit 1; done' "$D")" 'yes'
row 'settings.json has exactly one remote-setup SessionStart hook' "$(hooks "$R/.claude/settings.json")" '1'
row 'hook matcher is startup|resume' "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["hooks"]["SessionStart"][0]["matcher"])' "$R/.claude/settings.json")" 'startup|resume'
echo '=== never fires locally (SKILL.md: prints nothing, exit 0) ==='
out=$(env -u CLAUDE_CODE_REMOTE -u CLAUDE_CODE_ENTRYPOINT -u REMOTE_SETUP_FORCE HOME="$TMP/home" bash "$D/setup.sh" 2>&1); rc=$?
row 'generated setup.sh exits 0 locally' "$rc" '0'
row 'generated setup.sh prints nothing locally' "$([ -z "$out" ] && echo empty || echo output)" 'empty'
row 'generated setup.sh does not touch HOME locally' "$(yn test ! -e "$TMP/home")" 'yes'

echo '=== second run: overwrite, keep, no duplicate ==='
echo '# edited' >> "$D/setup.sh"; echo '# mine' >> "$D/steps.sh"; echo '# mine' >> "$D/environment-setup.sh"
python3 "$SCAFFOLD" "$R" >/dev/null; rc=$?
row 'exit status' "$([ $rc = 0 ] && echo ok || echo bad)" 'ok'
row 'setup.sh is overwritten from the template' "$(yn grep -q '^# edited' "$D/setup.sh")" 'no'
row 'steps.sh is kept' "$(yn grep -q '^# mine' "$D/steps.sh")" 'yes'
row 'environment-setup.sh is kept' "$(yn grep -q '^# mine' "$D/environment-setup.sh")" 'yes'
row 'hook is not added twice' "$(hooks "$R/.claude/settings.json")" '1'

echo '=== existing settings.json ==='
R2="$TMP/existing"; mkdir -p "$R2/.claude"
cat > "$R2/.claude/settings.json" <<'JSON'
{"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [{"matcher": "x", "hooks": [{"type": "command", "command": "echo other"}]}], "Stop": []}}
JSON
python3 "$SCAFFOLD" "$R2" >/dev/null
row 'keeps unrelated settings' "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["permissions"]["allow"][0])' "$R2/.claude/settings.json")" 'Bash(ls)'
row 'keeps the existing SessionStart hook' "$(grep -c 'echo other' "$R2/.claude/settings.json")" '1'
row 'adds the remote-setup hook next to it' "$(hooks "$R2/.claude/settings.json")" '1'

echo '=== bad arguments ==='
python3 "$SCAFFOLD" >/dev/null 2>&1; row 'no argument exits non-zero' "$([ $? != 0 ] && echo fail || echo ok)" 'fail'
python3 "$SCAFFOLD" a b >/dev/null 2>&1; row 'two arguments exit non-zero' "$([ $? != 0 ] && echo fail || echo ok)" 'fail'
python3 "$SCAFFOLD" "$TMP/missing" >/dev/null 2>&1; row 'a directory that does not exist exits non-zero' "$([ $? != 0 ] && echo fail || echo ok)" 'fail'
row 'and creates nothing' "$(yn test ! -e "$TMP/missing")" 'yes'
R3="$TMP/badjson"; mkdir -p "$R3/.claude"; echo '{not json' > "$R3/.claude/settings.json"
python3 "$SCAFFOLD" "$R3" >/dev/null 2>&1; row 'invalid settings.json exits non-zero' "$([ $? != 0 ] && echo fail || echo ok)" 'fail'
row 'and leaves the invalid settings.json as it was' "$(grep -c '^{not json$' "$R3/.claude/settings.json")" '1'
