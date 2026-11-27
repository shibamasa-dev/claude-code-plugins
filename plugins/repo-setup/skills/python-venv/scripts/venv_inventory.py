#!/usr/bin/env python3
"""List every Python venv under the given roots and flag the ones that look dead. Read-only.

Usage:
  venv_inventory.py [ROOT ...] [--shared-dir DIR] [--max-depth N]
                    [--stall-minutes M] [--stale-days D] [--json]

With no ROOT it scans the shared venv dir (--shared-dir, default ~/.venvs) and the home directory.
A venv is a directory holding a pyvenv.cfg file. For each one it reports:
  - size: apparent size of the files inside (uv may clone or hard-link files from its cache,
    so deleting a venv can free less than this)
  - created: mtime of pyvenv.cfg, which venv creation writes once and nothing rewrites later
  - last_modified: newest mtime of any entry inside the venv (an install touches site-packages,
    not the venv root)
  - deps_files: requirements*.txt / pyproject.toml in the directory that holds the venv
  - likely_dead: stalled (last change within --stall-minutes of creation) AND stale
    (last change at least --stale-days ago); never set when part of the venv could not be
    read (incomplete), because the unread part may hold newer changes

It skips node_modules, .git and Library/Caches, does not follow symlinks and does not look
for venvs inside a venv. It never deletes, writes or runs pip / uv. Missing or unreadable
paths are reported on stderr; the exit status is 0.
"""
import argparse
import datetime
import json
import os
import re
import stat
import sys
import time

SKIP_NAMES = {"node_modules", ".git"}
DEPS_FILE = re.compile(r"^(requirements.*\.txt|pyproject\.toml)$")


def warn(msg):
    print("venv_inventory: " + msg, file=sys.stderr)


def skipped(path, name):
    if name in SKIP_NAMES:
        return True
    return name == "Caches" and os.path.basename(os.path.dirname(path)) == "Library"


def is_venv(path):
    try:
        return stat.S_ISREG(os.lstat(os.path.join(path, "pyvenv.cfg")).st_mode)
    except OSError:
        return False


def find_venvs(root, max_depth):
    """Yield venv directories under root, at most max_depth levels below it (root itself is 0)."""
    stack = [(root, 0)]
    while stack:
        path, depth = stack.pop()
        if is_venv(path):
            yield path
            continue
        if depth >= max_depth:
            continue
        try:
            entries = list(os.scandir(path))
        except OSError as e:
            if path == root:
                warn("cannot read %s: %s" % (path, e.strerror))
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False) and not skipped(e.path, e.name):
                    stack.append((e.path, depth + 1))
            except OSError:
                continue


def measure(venv):
    """Return (apparent size in bytes, newest mtime, complete) of everything inside venv, without following symlinks.

    complete is False when some directory or entry inside could not be read."""
    size = 0
    complete = True
    newest = os.lstat(venv).st_mtime
    stack = [venv]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError as e:
            warn("cannot read %s: %s; its size and dates are incomplete" % (d, e.strerror))
            complete = False
            continue
        for e in entries:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError as err:
                warn("cannot read %s: %s; its size and dates are incomplete" % (e.path, err.strerror))
                complete = False
                continue
            newest = max(newest, st.st_mtime)
            if stat.S_ISDIR(st.st_mode):
                stack.append(e.path)
            else:
                size += st.st_size
    return size, newest, complete


def iso(t):
    return datetime.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def human(n):
    for unit in ("B", "K", "M", "G"):
        if n < 1024 or unit == "G":
            return ("%d%s" % (n, unit)) if unit == "B" else ("%.1f%s" % (n, unit))
        n /= 1024.0


def inspect(venv, now, stall_s, stale_s):
    created = os.lstat(os.path.join(venv, "pyvenv.cfg")).st_mtime
    size, last, complete = measure(venv)
    try:
        deps = sorted(n for n in os.listdir(os.path.dirname(venv)) if DEPS_FILE.match(n))
    except OSError:
        deps = []
    stalled = last - created <= stall_s
    stale = now - last >= stale_s
    return {
        "path": venv,
        "size_bytes": size,
        "created": iso(created),
        "last_modified": iso(last),
        "idle_days": int((now - last) // 86400),
        "deps_files": deps,
        "stalled": stalled,
        "stale": stale,
        "incomplete": not complete,
        "likely_dead": stalled and stale and complete,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="List Python venvs and flag likely dead ones (read-only).")
    p.add_argument("roots", nargs="*", help="directories to scan (default: the shared venv dir and ~)")
    p.add_argument("--shared-dir", default="~/.venvs", help="shared venv dir scanned when no ROOT is given (default ~/.venvs)")
    p.add_argument("--max-depth", type=int, default=6, help="deepest venv directory below a root (default 6)")
    p.add_argument("--stall-minutes", type=float, default=10, help="stalled: last change within this many minutes of creation (default 10)")
    p.add_argument("--stale-days", type=float, default=30, help="stale: no change for this many days (default 30)")
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")
    a = p.parse_args(argv)

    roots = a.roots or [a.shared_dir, "~"]
    now = time.time()
    seen, venvs, scanned = set(), [], []
    for r in roots:
        root = os.path.abspath(os.path.expanduser(r))
        if not os.path.isdir(root):
            warn("not a directory, skipped: %s" % root)
            continue
        scanned.append(root)
        for v in find_venvs(root, a.max_depth):
            key = os.path.realpath(v)
            if key in seen:
                continue
            seen.add(key)
            try:
                venvs.append(inspect(v, now, a.stall_minutes * 60, a.stale_days * 86400))
            except OSError as e:
                warn("cannot read %s: %s" % (v, e.strerror))
    venvs.sort(key=lambda v: v["path"])

    if a.json:
        json.dump({
            "generated_at": iso(now),
            "roots": scanned,
            "thresholds": {"stall_minutes": a.stall_minutes, "stale_days": a.stale_days, "max_depth": a.max_depth},
            "venvs": venvs,
        }, sys.stdout, indent=2)
        print()
        return 0

    for v in venvs:
        print("%-5s %8s  created %s  last %s  deps %-3s  %s" % (
            "DEAD" if v["likely_dead"] else ("?" if v["incomplete"] else "-"), human(v["size_bytes"]), v["created"][:10],
            v["last_modified"][:10], "yes" if v["deps_files"] else "no", v["path"]))
    dead = [v for v in venvs if v["likely_dead"]]
    print("%d venvs, %s; %d likely dead, %s" % (
        len(venvs), human(sum(v["size_bytes"] for v in venvs)), len(dead), human(sum(v["size_bytes"] for v in dead))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
