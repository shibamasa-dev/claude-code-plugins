#!/usr/bin/env python3
"""Group B (reviewer): pass references/reviewer-prompt.md to `claude -p` to review the fixture, verify quotes with
validate_findings.py, then count recall on the positives only the reviewer can catch and false positives on the negatives.

  python3 scripts/run_reviewer_eval.py [--runs 1] [--workers 3] [--timeout 600] [--keep DIR]

No model is specified (claude's default). The fixture content goes into the prompt with line numbers, plus the lint.py
results as hints. The fixture's author is not the person in this runtime environment, so this eval skips the
reviewer-prompt step "gather proper-noun hints from the runtime environment" (proper nouns are judged from the text alone).
Grading: each element of a positive's reviewer_expect (one expected finding) is a hit if the same file and line has a
valid finding whose quote contains any of the element's words.
For negatives, any valid finding on the same line is a false positive (for cases with reviewer_forbid_quote, only quotes containing it).
Pass bar: recall >= 0.8 and at most 1 false positive per run. exit 0 = bar met / 1 = not met.
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
import lint  # noqa: E402
import validate_findings as vf  # noqa: E402
from run_evals import load_spec, locate, materialize  # noqa: E402


def build_prompt(fixture):
    parts = [open(os.path.join(SKILL_DIR, "references", "reviewer-prompt.md"), encoding="utf-8").read()]
    parts.append("\n## Target skill (file contents with line numbers; read these instead of using tools)\n")
    for rel, ab, _ in lint.iter_files(fixture):
        text = lint.read_text(ab)
        if text is None:
            continue
        parts.append("### %s\n```" % rel)
        parts += ["%d: %s" % (i, l) for i, l in enumerate(text.splitlines(), 1)]
        parts.append("```")
    res = lint.lint(fixture, use_gitleaks=False)
    hints = [{k: f[k] for k in ("file", "line", "category", "match")} for f in res["findings"]]
    parts.append("\n## Hints: linter results\n```json\n%s\n```" % json.dumps(hints, ensure_ascii=False))
    parts.append("\n## Runtime environment hints\nThis eval does not gather hints from the runtime environment (run no commands). "
                 "Judge proper nouns from the target skill's text alone.")
    parts.append("\nAs instructed above, output only the JSON array.")
    return "\n".join(parts)


def run_claude(prompt, timeout):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    cwd = tempfile.mkdtemp(prefix="skill-lint-eval-")  # empty cwd: keep the project's CLAUDE.md out
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "5"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "seconds": timeout}
    out = {"seconds": round(time.time() - t0, 1), "returncode": r.returncode}
    try:
        j = json.loads(r.stdout)
        out["result"] = j.get("result", "")
        out["model"] = ",".join((j.get("modelUsage") or {}).keys()) or j.get("model", "")
    except ValueError:
        out["result"] = r.stdout
        out["stderr"] = r.stderr[-500:]
    return out


def score(spec, fixture, valid):
    pos_hits, pos_total, fps = [], 0, []
    for c in spec["cases"]:
        line = locate(fixture, c)
        at = [f for f in valid if f["file"] == c["file"] and f["line"] == line]
        if c["kind"] == "positive":
            for n, group in enumerate(c.get("reviewer_expect", []), 1):
                pos_total += 1
                if any(any(k in f["quote"] for k in group) for f in at):
                    pos_hits.append("%s-%d" % (c["id"], n))
        elif c["kind"] == "negative":
            if c.get("reviewer_forbid_quote"):
                at = [f for f in at if any(k in f["quote"] for k in c["reviewer_forbid_quote"])]
            fps += [{"case": c["id"], "quote": f["quote"], "category": f["category"]} for f in at]
    return pos_hits, pos_total, fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--keep", help="directory to keep raw output and validation results")
    a = ap.parse_args()
    spec = load_spec()
    with materialize(os.path.join(SKILL_DIR, spec["fixture_dir"])) as fixture:
        ok = evaluate(spec, fixture, a)
    sys.exit(0 if ok else 1)


def evaluate(spec, fixture, a):
    prompt = build_prompt(fixture)
    with ThreadPoolExecutor(a.workers) as ex:
        outs = list(ex.map(lambda _: run_claude(prompt, a.timeout), range(a.runs)))
    keep = a.keep or tempfile.mkdtemp(prefix="skill-lint-eval-out-")
    os.makedirs(keep, exist_ok=True)
    hits_sum = total_sum = 0
    ok = True
    for i, o in enumerate(outs, 1):
        arr = vf.extract_array(o.get("result", "")) if "result" in o else None
        if arr is None:
            print("run %d: cannot extract a JSON array (%s)" % (i, o.get("error") or o.get("stderr") or o.get("result", "")[:200]))
            ok = False
            continue
        v = vf.validate(fixture, arr)
        hits, total, fps = score(spec, fixture, v["valid"])
        hits_sum += len(hits)
        total_sum += total
        ok &= len(fps) <= 1
        json.dump({"raw": o, "validated": v, "hits": hits, "false_positives": fps},
                  open(os.path.join(keep, "run%d.json" % i), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("run %d (%ss, model=%s): recall %d/%d %s / negative false positives %d %s / findings %d (valid %d, invalid %d, invalid ratio %.2f)" % (
            i, o.get("seconds"), o.get("model") or "default", len(hits), total, hits, len(fps),
            [f["case"] + ":" + f["quote"] for f in fps], len(arr), len(v["valid"]), len(v["invalid"]), v["invalid_ratio"]))
        for x in v["invalid"]:
            print("    invalid: %s:%s %r (%s)" % (x.get("file"), x.get("line"), x.get("quote"), x["reason"]))
    recall = hits_sum / total_sum if total_sum else 0.0
    ok &= recall >= 0.8 and total_sum > 0
    print("\nTotal: recall %d/%d = %.2f (bar >= 0.80) / negative false positives <= 1 per run / result: %s" % (
        hits_sum, total_sum, recall, "bar met" if ok else "bar not met"))
    print("raw output: %s" % keep)
    return ok


if __name__ == "__main__":
    main()
