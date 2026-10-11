#!/bin/bash
# Record repo-structure-guard.py's verdict for every case. Evidence that "the verdicts match the previous version exactly".
# The output file can be given as an argument, so before/after runs can be saved separately and diffed.
set -u
OUT="${1:-/dev/stdout}"

F=/tmp/fg-fixture
rm -rf "$F"
# The two forms of the skill-layout exemption ((1) a skills path component (2) SKILL.md in the parent of scripts/)
mkdir -p "$F/repo/.git" "$F/repo/docs/spec" "$F/repo/scripts/sub" \
         "$F/repo/skills/alpha/docs" \
         "$F/skills/repo2/.git" "$F/skills/repo2/docs" "$F/skills/repo2/scripts" \
         "$F/repo/skills/alpha/scripts" \
         "$F/repo/deliverables/beta/scripts"
: > "$F/repo/deliverables/beta/SKILL.md"
: > "$F/repo/docs/EXISTS.md"          # for the overwrite-existing-file case
: > "$F/repo/scripts/exists.sh"

# The rule file (passed via REPO_STRUCTURE_SPEC). A minimal version with only the guard blocks the checks need.
export REPO_STRUCTURE_SPEC="$F/repo-structure.md"
cat > "$REPO_STRUCTURE_SPEC" <<'SPEC'
<!-- guard:docs-allow-filenames -->
- README.md
<!-- /guard:docs-allow-filenames -->
<!-- guard:docs-subfolders -->
- spec: what to build and how
- adr: why
- research: what we learned
- ops: how to run it
- reference: what is authoritative
<!-- /guard:docs-subfolders -->
<!-- guard:script-extensions -->
- .sh
- .py
- .js
- .ts
- .mjs
- .rb
- .zsh
- .bash
<!-- /guard:script-extensions -->
<!-- guard:exemptions -->
- path-component-skills: the whole tree where some path component is `skills`
- sibling-skill-md: when the parent directory of `scripts/` has a `SKILL.md`
<!-- /guard:exemptions -->
SPEC
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/repo-structure-guard.py"

probe() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
p = subprocess.run(["python3", os.environ["HOOK"]],
    input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": sys.argv[1]}}),
    capture_output=True, text=True)
o = p.stdout.strip()
print("allow" if not o else json.loads(o).get("hookSpecificOutput", {}).get("permissionDecision", "allow"))
PY
}

{
  echo "# repo-structure-guard.py verdicts"
  while IFS='|' read -r path label; do
    [ -z "$path" ] && continue
    printf '%-8s %s\n' "$(probe "$F/repo/$path")" "$label"
  done <<'CASES'
docs/foo.md|new .md directly under docs/
docs/README.md|docs/README.md (the only exception)
docs/readme.md|docs/readme.md (lowercase, not the exception)
docs/EXISTS.md|directly under docs/ but an existing file (out of scope)
docs/spec/foo.md|under docs/spec/
docs/foo.txt|directly under docs/ but not .md
scripts/foo.sh|new script directly under scripts/ (.sh)
scripts/foo.py|new script directly under scripts/ (.py)
scripts/foo.ts|new script directly under scripts/ (.ts)
scripts/foo.txt|directly under scripts/ but not a script extension
scripts/exists.sh|directly under scripts/ but an existing file (out of scope)
scripts/sub/foo.sh|under scripts/sub/
skills/alpha/scripts/foo.sh|skill exemption (1) skills path component
deliverables/beta/scripts/foo.sh|skill exemption (2) SKILL.md in the parent of scripts/
deliverables/gamma/scripts/foo.sh|directly under scripts/ with no exemption
src/foo.sh|neither docs/ nor scripts/
skills/alpha/docs/foo.md|directly under docs/ is not exempt even under skills
../skills/repo2/docs/foo.md|skills in the checkout path (docs/)
../skills/repo2/scripts/foo.sh|skills in the checkout path (scripts/)
CASES
} > "$OUT"
rm -rf "$F"
