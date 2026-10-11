#!/usr/bin/env python3
"""Deterministically check a skill for information specific to the environment that made it (skill-lint's preprocessing layer).

  python3 lint.py <skill directory> [--json] [--no-gitleaks]

Only generic regular expressions live here. Proper nouns such as people, companies and clients cannot be caught
by a regex, so the reviewer (an agent) judges them from hints it gathers from the runtime environment on the spot.
Only paths listed in the skill's `.skill-lint-ignore` (one pattern per line, relative to the directory holding that file,
a trailing `/` means a directory) are excluded. Nothing is excluded by default (fixtures taken from real data leak the most).
Lines containing `skill-lint: ignore` are not checked.
exit 0 = no errors (may contain warnings) / 1 = errors found / 2 = bad arguments.
"""
import argparse, fnmatch, json, os, re, shutil, subprocess, sys, tempfile

IGNORE_MARK = "skill-lint: ignore"
GITLEAKS_TIMEOUT = 120
SKIP_DIRS = {".git", "node_modules", "__pycache__"}
SKIP_FILES = {".DS_Store"}
IGNORE_FILE = ".skill-lint-ignore"
MANIFESTS = (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
RE_PUBLISHER = re.compile(r'^\s*"(?:name|author|owner|homepage|repository|url)"\s*:')  # publisher info in a manifest

SEVERITY = {"identity": "error", "path": "error", "network": "error", "structure": "error", "unreadable": "error",
            "secret": "error", "tracker": "warn", "provenance": "warn"}
FIX = {
    "identity": "Replace people, organization and account names with a role (\"the user\", \"the caller\", etc.), or delete the whole backstory parenthetical",
    "path": "Do not default to a personal directory. Take it from an argument or environment variable, and use a placeholder such as `<project-root>` in examples",
    "network": "Read host names from an environment variable or config file. Use placeholders in examples",
    "tracker": "Delete private issue/PR numbers and state the reason in the text if needed. For a public upstream reference, add `skill-lint: ignore` to the line",
    "provenance": "Delete the date and who decided; keep only the rule and its reason (the history belongs in git log / issues)",
    "structure": "Move runtime data outside the skill (e.g. `~/.local/state/<skill>/`) and delete it from the skill",
    "unreadable": "Make it readable and run again (unreadable files were not checked)",
    "secret": "Remove the secret and revoke the leaked value. If gitleaks failed, fix the cause and run again",
}
# Values of "gitleaks.status" in the --json output
GL_SKIPPED, GL_RAN, GL_FAILED = "skipped", "ran", "failed"

# Generic patterns (no concrete names)
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
RE_EMAIL_OK = re.compile(r"@(?:example\.(?:com|org|net)|users\.noreply\.github\.com)$")
RE_HOME_ABS = re.compile(r"(?:/Users/|/home/|[A-Za-z]:[\\/](?i:users)[\\/])([A-Za-z0-9._-]+)[/\\]")  # skill-lint: ignore
HOME_ABS_OK = {"Shared", "runner", "user", "username", "USER", "USERNAME", "you", "me", "name"}
RE_TILDE_PATH = re.compile(r"(?:~|\$HOME|\$\{HOME\})/[^\s`'\")\]>,;{}]+")
TILDE_OK_PREFIXES = ("/.claude/", "/.config/", "/.local/", "/.cache/")
# Home-relative paths outside the standard ones are a warning. In real data, tool locations (hidden directories right under
# home, the OS's standard folders) outnumber personal directory layouts (work folders someone set up), so an error would
# misfire more often than not. The reviewer decides
TILDE_SEVERITY = "warn"
RE_TAILNET = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.ts\.net\b")  # skill-lint: ignore
RE_TRACKER = re.compile(r"(?<![&\w#])(?:[\w.-]+/)?(?:[A-Za-z][\w.-]*)?#\d+(?![\w])")
# Dates and decision words are Japanese on purpose: they detect Japanese decision-history phrases
# ("<date> ... confirmed / approved / instructed / decided / checked")
RE_DATE = re.compile(r"(?<!\d)(?:20\d{2}-\d{1,2}-\d{1,2}|20\d{2}/\d{1,2}/\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)(?!\d)")
RE_DECISION = re.compile(r"確定|承認|指示|判断|確認")
RE_FM_SKIP = re.compile(r"^\s*(?:last_reviewed|review_after)\s*:")
STRUCT_DIRS = {"logs", ".trash"}
STRUCT_GLOBS = ("*.db", "*.db-wal", "*.db-shm", "*.sqlite", "*.sqlite3", "*.jsonl", "*.log")


def read_ignore(d):
    path = os.path.join(d, IGNORE_FILE)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def ignored(rel, pats):
    for p in pats:
        if p.endswith("/") and (rel + "/").startswith(p):
            return True
        if fnmatch.fnmatch(rel, p):
            return True
    return False


def iter_files(root):
    """Yield (relative path, absolute path, excluded?). Exclusion follows the .skill-lint-ignore at each level."""
    rules = []  # (directory holding the ignore file, patterns)
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        pats = read_ignore(d)
        if pats:
            rules.append((d, pats))
        for f in sorted(files):
            if f in SKIP_FILES:
                continue
            ab = os.path.join(d, f)
            rel = os.path.relpath(ab, root).replace(os.sep, "/")
            ex = any(ignored(os.path.relpath(ab, base).replace(os.sep, "/"), p)
                     for base, p in rules if (ab + os.sep).startswith(base + os.sep))
            yield rel, ab, ex


def structure_findings(rel):
    parts = rel.split("/")
    out = []
    for p in parts[:-1]:
        if p in STRUCT_DIRS:
            out.append(("runtime data under %s/" % p, p + "/"))
            break
    if any(fnmatch.fnmatch(parts[-1], g) for g in STRUCT_GLOBS):
        out.append(("extension that looks like runtime data", parts[-1]))
    return out


def read_text(ab):
    """Return the text. None for binary files; an unreadable file raises OSError as is (never skipped silently)."""
    with open(ab, "rb") as f:
        b = f.read()
    if b"\0" in b[:8192]:
        return None
    return b.decode("utf-8", errors="replace")


def scan_line(line):
    """Return (category, match, message, severity or None) for one line. None means the category's default severity."""
    hits = []
    for m in RE_EMAIL.finditer(line):
        if not RE_EMAIL_OK.search(m.group(0)):
            hits.append(("identity", m.group(0), "email address", None))
    for m in RE_HOME_ABS.finditer(line):
        if m.group(1) not in HOME_ABS_OK:
            hits.append(("path", m.group(0), "absolute path under a user's home", None))
    for m in RE_TILDE_PATH.finditer(line):
        s = m.group(0)
        rest = s[s.index("/"):]
        if rest.startswith(TILDE_OK_PREFIXES):
            continue
        hits.append(("path", s, "home-relative path outside the standard ones (check it is not a personal directory layout)", TILDE_SEVERITY))
    for m in RE_TAILNET.finditer(line):
        hits.append(("network", m.group(0), "tailnet host name", None))
    for m in RE_TRACKER.finditer(line):
        hits.append(("tracker", m.group(0), "issue/PR number reference", None))
    d = RE_DATE.search(line)
    k = RE_DECISION.search(line)
    if d and k:
        hits.append(("provenance", "%s … %s" % (d.group(0), k.group(0)), "dated decision history", None))
    return hits


def run_gitleaks(root):
    exe = shutil.which("gitleaks")
    if not exe:
        return {"status": GL_SKIPPED, "reason": "gitleaks is not on PATH"}
    fd, rep = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        for args in (["dir", root], ["detect", "--no-git", "--source", root]):
            try:
                r = subprocess.run([exe] + args + ["--no-banner", "--report-format", "json", "--report-path", rep, "--exit-code", "0"],
                                   capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=GITLEAKS_TIMEOUT)
            except subprocess.TimeoutExpired:
                return {"status": GL_FAILED, "reason": "gitleaks did not finish within %d seconds" % GITLEAKS_TIMEOUT}
            if r.returncode == 0:
                try:
                    with open(rep, encoding="utf-8") as f:
                        leaks = json.load(f) or []
                except ValueError as e:  # an unreadable report must not become "0 found"
                    return {"status": GL_FAILED, "reason": "cannot read the gitleaks report (%s)" % e}
                return {"status": GL_RAN, "leaks": [
                    {"file": os.path.relpath(x.get("File", ""), root).replace(os.sep, "/"), "line": x.get("StartLine"), "rule": x.get("RuleID")}
                    for x in leaks]}
        return {"status": GL_FAILED, "reason": (r.stderr or r.stdout).strip()[:300]}
    finally:
        os.unlink(rep)


def lint(root, use_gitleaks=True):
    root = os.path.abspath(os.path.expanduser(root))
    findings, excluded, scanned = [], [], 0
    for rel, ab, is_excluded in iter_files(root):
        if is_excluded:
            excluded.append(rel)
            continue
        scanned += 1
        for msg, m in structure_findings(rel):
            findings.append({"file": rel, "line": 0, "category": "structure", "match": m, "message": msg, "text": ""})
        try:
            text = read_text(ab)
        except OSError as e:
            findings.append({"file": rel, "line": 0, "category": "unreadable", "match": "", "message": "unreadable, so not checked (%s)" % e.strerror, "text": ""})
            continue
        if text is None:
            continue
        lines = text.splitlines()
        fm_end = 0
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    fm_end = i
                    break
        for i, line in enumerate(lines, 1):
            if IGNORE_MARK in line:
                continue
            if i - 1 <= fm_end and fm_end and RE_FM_SKIP.match(line):
                continue
            publisher = rel.endswith(MANIFESTS) and RE_PUBLISHER.match(line)
            for cat, m, msg, sev in scan_line(line):
                if publisher and cat == "identity":  # the publisher's name and contact are public by design; paths and hosts are still checked
                    continue
                findings.append({"file": rel, "line": i, "category": cat, "match": m, "message": msg,
                                 "text": line.strip()[:200], "severity": sev})
    gl = run_gitleaks(root) if use_gitleaks else {"status": GL_SKIPPED, "reason": "--no-gitleaks"}
    for x in gl.get("leaks", []):
        if x["file"] not in excluded:
            findings.append({"file": x["file"], "line": x["line"] or 0, "category": "secret", "match": x["rule"],
                             "message": "gitleaks found a secret (%s)" % x["rule"], "text": ""})
    if gl["status"] == GL_FAILED:
        findings.append({"file": "", "line": 0, "category": "secret", "match": "",
                         "message": "gitleaks failed, so secrets were not checked", "text": gl.get("reason", "")})
    for f in findings:
        f["severity"] = f.get("severity") or SEVERITY[f["category"]]
        f["fix"] = FIX[f["category"]]
    return {
        "root": root,
        "scanned_files": scanned,
        "excluded_files": excluded,
        "gitleaks": gl,
        "summary": {"error": sum(f["severity"] == "error" for f in findings),
                    "warn": sum(f["severity"] == "warn" for f in findings)},
        "findings": findings,
    }


def print_human(res):
    print("Target: %s (%d files, %d excluded by .skill-lint-ignore)" % (res["root"], res["scanned_files"], len(res["excluded_files"])))
    print("Proper nouns (people, companies, clients): not checked by lint. The reviewer judges them")
    g = res["gitleaks"]
    print("gitleaks: %s" % (g["status"] + (" (%s)" % g["reason"] if g.get("reason") else " (%d found)" % len(g.get("leaks", [])))))
    for x in g.get("leaks", []):
        print("  secret: %s:%s %s" % (x["file"], x["line"], x["rule"]))
    order = ["secret", "identity", "path", "network", "structure", "tracker", "provenance"]
    for cat in order:
        fs = [f for f in res["findings"] if f["category"] == cat]
        if not fs:
            continue
        print("\n%s: %d — fix: %s" % (cat, len(fs), FIX[cat]))
        for f in fs:
            loc = "%s:%d" % (f["file"], f["line"]) if f["line"] else f["file"]
            print("  [%s] %s  %s \"%s\"" % (f["severity"], loc, f["message"], f["match"]))
    s = res["summary"]
    print("\nTotal: error %d / warn %d" % (s["error"], s["warn"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("skill_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-gitleaks", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(os.path.expanduser(a.skill_dir)):
        print("No such directory: %s" % a.skill_dir, file=sys.stderr)
        sys.exit(2)
    res = lint(a.skill_dir, not a.no_gitleaks)
    if a.json:
        json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print_human(res)
    sys.exit(1 if res["summary"]["error"] else 0)


if __name__ == "__main__":
    main()
