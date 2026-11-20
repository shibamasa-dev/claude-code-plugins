#!/bin/bash
# Measures skill-lint's offline scripts: lint.py (deterministic leak patterns) and validate_findings.py (drops findings whose quote is not on the line).
# Clean input is a copy of a real skill of this repo (remote-setup); the leaks are planted into the copy with made-up values.
# Not covered on purpose: run_evals.py and run_reviewer_eval.py (they need the unpublished evals/ set; the second also needs the claude CLI).
set -u
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SL="$ROOT/plugins/lint/skills/skill-lint/scripts"
SRC="$ROOT/plugins/repo-setup/skills/remote-setup"
TMP=$(mktemp -d) || exit 1; trap 'rm -rf "$TMP"' EXIT
row() {  # row <description> <got> <want>: the verdict is ok when got equals want (run-all.sh reads lowercase words after ->)
  if [ "$2" = "$3" ]; then printf '  %-62s -> ok (expect ok)\n' "$1"; else printf '  %s [got: %s, want: %s] -> bad (expect ok)\n' "$1" "$2" "$3"; fi
}
# Parts are joined here so this file itself carries no home path or host name
HOMEDIR="/Us""ers/alice"; HOST="acme-internal.tail1234.ts"".net"; MAIL="bob@acme-internal""-corp.io"

lint() { python3 "$SL/lint.py" "$@" --no-gitleaks; }
# cats <dir>: sorted unique "category:severity" pairs from --json
cats() { lint "$1" --json | python3 -c 'import json,sys; print(" ".join(sorted({f["category"]+":"+f["severity"] for f in json.load(sys.stdin)["findings"]})) or "none")'; }
fresh() { rm -rf "$TMP/s"; cp -R "$SRC" "$TMP/s"; }

echo '=== lint.py on a real clean skill ==='
fresh; lint "$TMP/s" >/dev/null; row 'exit 0 for the clean skill (warnings allowed)' "$?" '0'
row 'no error-level finding' "$(lint "$TMP/s" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["summary"]["error"])')" '0'

echo '=== planted leaks ==='
fresh; echo "Default dir: $HOMEDIR/work" >> "$TMP/s/SKILL.md"; lint "$TMP/s" >/dev/null
row 'home absolute path: exit 1' "$?" '1'
row 'home absolute path is reported as path:error' "$(cats "$TMP/s" | tr ' ' '\n' | grep -c '^path:error$')" '1'
fresh; echo "ssh $HOST" >> "$TMP/s/SKILL.md"; row 'tailnet host name gives network:error' "$(cats "$TMP/s" | tr ' ' '\n' | grep '^network')" 'network:error'
fresh; echo "Contact $MAIL" >> "$TMP/s/SKILL.md"; row 'email address gives identity:error' "$(cats "$TMP/s" | tr ' ' '\n' | grep '^identity')" 'identity:error'
fresh; echo "Contact someone@example.com" >> "$TMP/s/SKILL.md"; row 'example.com address is allowed' "$(cats "$TMP/s" | tr ' ' '\n' | grep -c '^identity')" '0'
fresh; echo "See acme-internal/repo#123 for details" >> "$TMP/s/SKILL.md"; lint "$TMP/s" >/dev/null
row 'issue number gives tracker:warn, exit stays 0' "$(cats "$TMP/s" | tr ' ' '\n' | grep '^tracker'):$?" 'tracker:warn:0'
fresh; echo "2026-01-02 approved by the team" >> "$TMP/s/SKILL.md"; row 'dated decision gives provenance:warn' "$(cats "$TMP/s" | tr ' ' '\n' | grep '^provenance')" 'provenance:warn'
fresh; mkdir "$TMP/s/logs"; echo x > "$TMP/s/logs/a.txt"; row 'runtime data dir logs/ gives structure:error' "$(cats "$TMP/s" | tr ' ' '\n' | grep '^structure')" 'structure:error'
fresh; echo x > "$TMP/s/data.sqlite"; row 'runtime data extension gives structure:error' "$(cats "$TMP/s" | tr ' ' '\n' | grep '^structure')" 'structure:error'

echo '=== exclusions ==='
fresh; echo "Default dir: $HOMEDIR/work skill-lint: ignore" >> "$TMP/s/SKILL.md"; lint "$TMP/s" >/dev/null
row 'a line with the ignore mark is not checked' "$?" '0'
fresh; echo "Default dir: $HOMEDIR/work" > "$TMP/s/notes.md"; echo 'notes.md' > "$TMP/s/.skill-lint-ignore"; lint "$TMP/s" >/dev/null
row 'a file listed in .skill-lint-ignore is not checked' "$?" '0'
fresh; echo "Default dir: $HOMEDIR/work" > "$TMP/s/notes.md"; lint "$TMP/s" >/dev/null
row 'the same file without the ignore list is an error' "$?" '1'

echo '=== lint.py arguments ==='
lint "$TMP/nope" >/dev/null 2>&1; row 'missing directory exits 2' "$?" '2'

echo '=== validate_findings.py ==='
fresh; printf 'alpha line\nbeta line\n' > "$TMP/s/f.txt"
vf() { python3 "$SL/validate_findings.py" "$TMP/s" "$@"; }
counts() { python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["valid"]), len(d["invalid"]))'; }
F='"category":"path","fix":"x","confidence":"high"'
printf '[{"file":"f.txt","line":2,"quote":"beta",%s}]' "$F" > "$TMP/ok.json"
row 'quote found on its line is valid' "$(vf "$TMP/ok.json" | counts)" '1 0'
printf '[{"file":"f.txt","line":1,"quote":"beta",%s}]' "$F" > "$TMP/wrong.json"
row 'quote on a different line is invalid' "$(vf "$TMP/wrong.json" | counts)" '0 1'
printf '[{"file":"f.txt","line":9,"quote":"beta",%s}]' "$F" > "$TMP/range.json"
row 'line number out of range is invalid' "$(vf "$TMP/range.json" | counts)" '0 1'
printf '[{"file":"missing.txt","line":1,"quote":"beta",%s}]' "$F" > "$TMP/nofile.json"
row 'a file that does not exist is invalid' "$(vf "$TMP/nofile.json" | counts)" '0 1'
printf '[{"file":"../outside.txt","line":1,"quote":"x",%s}]' "$F" > "$TMP/esc.json"; echo x > "$TMP/outside.txt"
row 'a path escaping the skill directory is invalid' "$(vf "$TMP/esc.json" | counts)" '0 1'
printf '[{"file":"f.txt","line":1,"quote":"alpha"}]' > "$TMP/fields.json"
row 'missing required fields is invalid' "$(vf "$TMP/fields.json" | counts)" '0 1'
printf 'Here is my review:\n```json\n[{"file":"f.txt","line":1,"quote":"alpha",%s}]\n```\nDone.\n' "$F" > "$TMP/fence.txt"
row 'JSON inside a fence with prose around it is read' "$(vf "$TMP/fence.txt" | counts)" '1 0'
printf '[{"file":"f.txt","line":1,"quote":"alpha",%s},{"file":"f.txt","line":1,"quote":"zzz",%s}]' "$F" "$F" > "$TMP/half.json"
row 'invalid_ratio is invalid / total' "$(vf "$TMP/half.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["invalid_ratio"])')" '0.5'
echo 'no findings here' > "$TMP/none.txt"; vf "$TMP/none.txt" >/dev/null 2>&1
row 'output without a JSON array exits 2' "$?" '2'
python3 "$SL/validate_findings.py" >/dev/null 2>&1; row 'no arguments exits 2' "$?" '2'
