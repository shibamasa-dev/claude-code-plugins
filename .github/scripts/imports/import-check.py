#!/usr/bin/env python3
"""Execute every plugin Python file at module level, without running its main, on the current interpreter.

py_compile only parses a file. An annotation such as `str | None` parses on Python 3.9 and fails only when the
module body runs (the def statement evaluates it), so this runs each module body the way `import` would:
runpy.run_path with __name__ set to something other than "__main__", so `if __name__ == "__main__": main()` is skipped.

  python3 .github/scripts/imports/import-check.py            # every tracked plugins/**/*.py
  python3 .github/scripts/imports/import-check.py FILE...    # only these files

Each file runs in its own child process with HOME, TMPDIR and the working directory pointed at a temp directory that
is removed afterwards, CLAUDE_PLUGIN_DATA / CLAUDE_PROJECT_DIR unset and bytecode writing off, so a module that
resolves a state directory at import time writes nothing outside that temp directory. No network is used.
Exits 1 and prints the file name and the error for every file that fails.
"""
import os
import shutil
import subprocess
import sys
import tempfile

# Repo-relative files whose module body must not run here, each with the reason. Keep this empty unless a module has
# an import-time side effect that the temp HOME / cwd cannot contain.
EXCLUDE = {}

CHILD = r"""
import os, runpy, sys
path = sys.argv[1]
sys.path.insert(0, os.path.dirname(path))  # what `python3 path` does, so sibling imports (_state, _shell) resolve
sys.argv = [path]
runpy.run_path(path, run_name="__import_check__")
"""


def tracked_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--", "plugins/*.py"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(f for f in out.split("\0") if f)


def check(path, tmp):
    """Run one module body in a child process. Returns None when it ran, else the last line of the error."""
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_DATA", "CLAUDE_PROJECT_DIR", "PYTHONPATH")}
    home = os.path.join(tmp, "home")
    os.makedirs(home)
    env.update(HOME=home, TMPDIR=tmp, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([sys.executable, "-c", CHILD, os.path.abspath(path)], cwd=tmp, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "timed out after 60s (does the module body wait for input or the network?)"
    if r.returncode == 0:
        return None
    lines = [l for l in r.stderr.strip().splitlines() if l.strip()]
    return lines[-1] if lines else f"exit {r.returncode} with no message"


def main():
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                          check=True).stdout.strip()
    files = sys.argv[1:] or [os.path.join(root, f) for f in tracked_files(root)]
    print(f"Python {sys.version.split()[0]} ({sys.executable}): executing {len(files)} module bodies")
    failed = 0
    for f in files:
        absf = os.path.abspath(f)
        rel = os.path.relpath(absf, root) if absf.startswith(root + os.sep) else f
        if rel in EXCLUDE:
            print(f"  skip {rel}: {EXCLUDE[rel]}")
            continue
        tmp = tempfile.mkdtemp(prefix="import-check.")
        try:
            err = check(absf, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if err:
            failed += 1
            print(f"  FAIL {rel}: {err}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::error file={rel}::{err}")
        else:
            print(f"  ok   {rel}")
    print(f"{len(files) - failed} ok / {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
