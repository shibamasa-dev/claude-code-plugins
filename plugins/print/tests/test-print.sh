#!/bin/bash
# Runs the print skill's cases (tests/cases.json) offline and prints one verdict row per case.
# Every case runs print.py with --dry-run, a fixed --printer and a saved lpoptions file. On top of that, lp, lpstat,
# lpoptions and cancel are shimmed first on PATH: a shim records its call and fails, so the last row checks that
# nothing reached CUPS. Cases whose "requires" tools (qpdf, Chrome) are missing print a SKIP line, which is not a
# verdict row and does not count as checked.
cd "$(dirname "$0")" || exit 1
shims=$(mktemp -d "${TMPDIR:-/tmp}/print-test.XXXXXX")
trap 'rm -rf "$shims"' EXIT
for c in lp lpstat lpoptions cancel; do
  printf '#!/bin/sh\necho "%s $*" >> "%s/calls"\nexit 1\n' "$c" "$shims" > "$shims/$c"
  chmod +x "$shims/$c"
done
PATH="$shims:$PATH" python3 -I - <<'PY'
import json, os, shutil, subprocess, sys

def have(tool):
    if tool == "chrome":
        return any(os.access(p, os.X_OK) for p in [
            os.environ.get("CHROME", ""),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium"]) or any(
            shutil.which(c) for c in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"])
    return shutil.which(tool) is not None

spec = json.load(open("cases.json", encoding="utf-8"))
for case in spec["cases"]:
    missing = [t for t in case.get("requires", []) if not have(t)]
    if missing:
        print("  SKIP %s: %s not found" % (case["id"], ", ".join(missing)))
        continue
    cmd = ["python3", "../skills/print/scripts/print.py", *case["args"], "--printer", "EVAL_PRINTER",
           "--lpoptions-file", case["lpoptions"], "--dry-run"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    errs = ["exit %d: %s" % (r.returncode, r.stderr.strip())] if r.returncode else []
    errs += ["missing: %s" % s for s in case["expect_contains"] if s not in r.stdout]
    errs += ["unexpected: %s" % s for s in case.get("expect_not_contains", []) if s in r.stdout]
    for e in errs:
        print("     " + e)
    if errs:
        print("\n".join("     | " + l for l in r.stdout.splitlines()))
    print("  %s -> %s (expect ok)" % (case["id"], "failed" if errs else "ok"))
PY
rc=$?   # a crashed runner (bad cases.json, an exception) must fail the script, not vanish behind the rows below
n=0; [ -f "$shims/calls" ] && { cat "$shims/calls"; n=$(wc -l < "$shims/calls" | tr -d ' '); }
printf '  calls to lp / lpstat / lpoptions / cancel -> %s (expect 0)\n' "$n"
exit "$rc"
