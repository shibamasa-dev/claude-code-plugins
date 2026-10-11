#!/usr/bin/env python3
"""Group A (deterministic): run lint.py on the fixture and compare against the expected categories in evals/evals.json.

  python3 scripts/run_evals.py [case ID ...]

Grading: for positives, lint_expect ⊆ the categories reported on that line (if lint_expect_match is set, a match containing
that string is also required); for both negatives and positives, lint_forbid ∩ the reported categories = ∅.
A line is located by file and anchor (a fragment unique within the line). A case with no anchor means line 0 (a file-level finding).
Two fixture lines store the parts that would trip the public repo's leak check (home absolute path, email address)
as tokens ({{USERS_DIR}}, {{AT}}). materialize() expands them into a temporary directory before linting, so the lines
lint sees are verbatim. The expanded files are never left in the repo.
exit 0 = all PASS / 1 = some FAIL.
"""
import contextlib, json, os, shutil, sys, tempfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
import lint  # noqa: E402


# Do not write the strings that trip the check verbatim in this file either (build them by concatenation)
TOKENS = {"{{USERS_DIR}}": "/" + "Us" + "ers/", "{{AT}}": "@"}


@contextlib.contextmanager
def materialize(src):
    """Copy the fixture to a temporary directory, expand the tokens and yield its path. Removed on exit."""
    tmp = tempfile.mkdtemp(prefix="skill-lint-fixture-")
    dst = os.path.join(tmp, os.path.basename(src))
    try:
        shutil.copytree(src, dst)
        for d, _, files in os.walk(dst):
            for f in files:
                p = os.path.join(d, f)
                s = open(p, encoding="utf-8").read()
                for k, v in TOKENS.items():
                    s = s.replace(k, v)
                open(p, "w", encoding="utf-8").write(s)
        yield dst
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def locate(fixture, case):
    """Return the line number containing the anchor. None if not found or found more than once."""
    if case.get("anchor") is None:
        return 0 if os.path.exists(os.path.join(fixture, case["file"])) else None
    lines = open(os.path.join(fixture, case["file"]), encoding="utf-8").read().splitlines()
    hits = [i for i, l in enumerate(lines, 1) if case["anchor"] in l]
    return hits[0] if len(hits) == 1 else None


def main():
    spec = json.load(open(os.path.join(SKILL_DIR, "evals", "evals.json"), encoding="utf-8"))
    with materialize(os.path.join(SKILL_DIR, spec["fixture_dir"])) as fixture:
        ok = grade(spec, fixture, set(sys.argv[1:]))
    sys.exit(0 if ok else 1)


def grade(spec, fixture, only):
    res = lint.lint(fixture, use_gitleaks=False)
    passed = failed = 0
    for c in spec["cases"]:
        if only and c["id"] not in only:
            continue
        line = locate(fixture, c)
        if line is None:
            failed += 1
            print("FAIL %s: cannot locate the fixture line (%s / %r)" % (c["id"], c["file"], c.get("anchor")))
            continue
        got = sorted({f["category"] for f in res["findings"] if f["file"] == c["file"] and f["line"] == line})
        matches = [f["match"] for f in res["findings"] if f["file"] == c["file"] and f["line"] == line]
        missing = [x for x in c["lint_expect"] if x not in got]
        missing += ["match:" + m for m in c.get("lint_expect_match", []) if not any(m in x for x in matches)]
        forbidden = [x for x in c["lint_forbid"] if x in got]
        ok = not missing and not forbidden
        passed += ok
        failed += not ok
        detail = "expected %s / got %s" % (c["lint_expect"] or "none", got or "none")
        if missing:
            detail += " / missing %s" % missing
        if forbidden:
            detail += " / forbidden %s" % forbidden
        print("%s %s (%s:%d): %s" % ("PASS" if ok else "FAIL", c["id"], c["file"], line, detail))
    total = passed + failed
    print("\npass_rate: %d/%d = %.2f" % (passed, total, passed / total if total else 0))
    return failed == 0 and total > 0


if __name__ == "__main__":
    main()
