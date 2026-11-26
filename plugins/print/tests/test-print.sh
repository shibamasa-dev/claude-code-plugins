#!/bin/bash
# Runs the print skill's cases (tests/cases.json) offline and prints one verdict row per case.
# Every case runs print.py with --dry-run, a fixed --printer and a saved lpoptions file. On top of that, lp, lpstat,
# lpoptions and cancel are shimmed first on PATH: a shim records its call and fails, so the last row checks that
# nothing reached CUPS. Cases whose "requires" tools (qpdf, Chrome) are missing print a SKIP line, which is not a
# verdict row and does not count as checked. A case with "expect_files" also passes --keep-pdf and checks each file
# on the lp command line (pages, text). print.py runs with its own TMPDIR, so the last row can check that it left no
# print-skill.* work directory behind.
cd "$(dirname "$0")" || exit 1
shims=$(mktemp -d "${TMPDIR:-/tmp}/print-test.XXXXXX")
trap 'rm -rf "$shims"' EXIT
for c in lp lpstat lpoptions cancel; do
  printf '#!/bin/sh\necho "%s $*" >> "%s/calls"\nexit 1\n' "$c" "$shims" > "$shims/$c"
  chmod +x "$shims/$c"
done
mkdir "$shims/tmp"
PATH="$shims:$PATH" PRINT_TEST_TMP="$shims/tmp" python3 -I - <<'PY'
import json, os, re, shlex, shutil, subprocess, sys

def have(tool):
    if tool == "chrome":
        return any(os.access(p, os.X_OK) for p in [
            os.environ.get("CHROME", ""),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium"]) or any(
            shutil.which(c) for c in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"])
    return shutil.which(tool) is not None

def check_files(stdout, expected):
    """Check each file lp would get against {pages, text}, in order."""
    cmd = next((l[len("Command: "):] for l in stdout.splitlines() if l.startswith("Command: ")), None)
    if cmd is None:
        return ["no Command line"]
    words = shlex.split(cmd)
    files = words[words.index("--") + 1:]
    if len(files) != len(expected):
        return ["lp gets %d files, expected %d" % (len(files), len(expected))]
    if len(set(files)) != len(files):
        return ["lp gets the same file twice: %s" % files]
    errs = []
    for f, want in zip(files, expected):
        info = subprocess.run(["pdfinfo", f], capture_output=True, text=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", info, re.M)
        pages = int(m.group(1)) if m else None
        text = subprocess.run(["pdftotext", f, "-"], capture_output=True, text=True).stdout
        if pages != want["pages"]:
            errs.append("%s: %s pages, expected %d" % (f, pages, want["pages"]))
        if want["text"] not in text:
            errs.append("%s: no %r in its text" % (f, want["text"]))
    return errs

env = dict(os.environ, TMPDIR=os.environ["PRINT_TEST_TMP"])
spec = json.load(open("cases.json", encoding="utf-8"))
for case in spec["cases"]:
    missing = [t for t in case.get("requires", []) if not have(t)]
    if missing:
        print("  SKIP %s: %s not found" % (case["id"], ", ".join(missing)))
        continue
    cmd = ["python3", "../skills/print/scripts/print.py", *case["args"], "--printer", "EVAL_PRINTER",
           "--lpoptions-file", case["lpoptions"], "--dry-run"]
    if "expect_files" in case:
        cmd.append("--keep-pdf")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    errs = ["exit %d: %s" % (r.returncode, r.stderr.strip())] if r.returncode else []
    if "expect_files" in case:
        errs += check_files(r.stdout, case["expect_files"])
        m = re.search(r"^Converted files kept in: (.+) \(remove it when done\)$", r.stdout, re.M)
        if m:
            shutil.rmtree(m.group(1), ignore_errors=True)
        else:
            errs.append("missing: Converted files kept in: ...")
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
left=$(find "$shims/tmp" -maxdepth 1 -name 'print-skill.*' | wc -l | tr -d ' ')
printf '  print-skill.* work directories left behind -> %s (expect 0)\n' "$left"
exit "$rc"
