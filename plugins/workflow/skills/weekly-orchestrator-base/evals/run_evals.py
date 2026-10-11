"""Run the weekly-orchestrator-base evals with zero manual steps (standard library only).

  python3 evals/run_evals.py                          # all cases (serial)
  python3 evals/run_evals.py --jobs 3                 # run 3 cases in parallel
  python3 evals/run_evals.py --case 1 --case 4
  python3 evals/run_evals.py --grade-only <run_dir>   # re-grade existing answers

For each case:
  1. executor: a fresh `claude -p` reads SKILL.md, solves the prompt as a dry run, and saves answer.md
  2. grader  : a separate `claude -p` checks answer.md against the assertions and writes grading.json
  3. tally   : print pass_rate and write run_dir/summary.json

Every situation is a fictional setup written in the prompt (GitHub is not consulted). The executor only gets
Read/Glob/Grep, so it physically cannot run gh or write anything (the dry run is enforced by tool limits).
The executor's cwd is an empty temporary directory so that no project's CLAUDE.md or skills get mixed in.
The executor and grader run as separate processes so the author does not grade its own answer.

Originally the run_evals.py of the project version of weekly-orchestrator. Requires: claude CLI (on PATH).
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SKILL = Path(__file__).resolve().parent.parent          # .../skills/weekly-orchestrator-base
EVALS = SKILL / "evals"
TOOLS = "Read,Glob,Grep"
GRADER_TOOLS = "Read,Write"
MAIN = (1, 2, 3, 4)

EXECUTOR = """You are a project's weekly orchestrator agent. Read the following skill and answer the request following its practices.

Skill: {skill}/SKILL.md (references/ is in the same directory)

## This is a dry run
- The situation in the request is a fictional setup. Do not look at real things such as GitHub or session lists; answer only from the state written in the request
- Do **not** create, edit, or close issues, operate on PRs, start subagents, spawn_task, or separate sessions, use SendMessage or archive_session,
  or create or edit files. Instead, write in your answer "what you would actually run, with what content, and in what order"
- Where confirmation from the user is needed, write what you would confirm in your answer, and decide per the skill, and write, whether to stop there or proceed
- Today is {today}

## Request
{prompt}

## Output
Following the skill's practices, return your final answer (decisions and reasons, operations to run, content to write, prompts) as one coherent piece of text.
"""

GRADER = """You are an eval grader. Read the answer and judge each assertion as PASS / FAIL, one by one.

## Answer to grade
{answer_path}
(Read the full text with the Read tool)

## Expected content (for reference; it does not take precedence over the assertions)
{expected}

## assertions
{assertions}

## Criteria
- PASS: the answer contains a concrete statement showing the assertion is true
- FAIL: no such statement / it contradicts / it only satisfies it superficially (only the conclusion matches with no reasoning, etc.)
- When in doubt, FAIL. The burden of proof is on the assertion
- Put a **quote** from the answer in evidence (part of the original text, not a summary)

## Output
Using the Write tool, write **only** JSON of the following shape to {out_path} (add no explanation before or after).

{{
  "expectations": [
    {{"text": "<the assertion's text, copied verbatim>", "passed": true, "evidence": "<quote from the answer>"}}
  ],
  "summary": {{"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0}}
}}
"""


def run_claude(prompt: str, cwd: Path, timeout: int, tools: str) -> str:
    """Call claude -p with CLAUDECODE removed (because it is launched nested inside Claude Code)."""
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    p = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text", "--allowedTools", tools],
        # Set encoding explicitly. Windows defaults to CP932, while claude's non-ASCII (e.g. Japanese) answers are UTF-8
        cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(f"claude -p exited {p.returncode}: {p.stderr[-2000:]}")
    return p.stdout


def read_grading(path: Path, asserts: list[str]) -> list[dict]:
    """Read grading.json and check that it maps one-to-one to the assertions.

    LLM output is nondeterministic: it may return only 1 of 7 items, duplicate items, or return passed as a string.
    If the denominator came only from the returned array, grading just 1 item would give 1/1 = 100% and the main cases would pass.
    Anything that fails this check is treated as a grading failure, kept distinct from a perfect score.
    """
    norm = lambda s: " ".join(str(s).split())
    g = json.loads(path.read_text(encoding="utf-8"))
    # Check types before calling .get() (the grader can write any JSON, so an array, string, or null may come back)
    if not isinstance(g, dict):
        raise ValueError(f"grading.json root is not an object ({type(g).__name__})")
    exps = g.get("expectations")
    if not isinstance(exps, list):
        raise ValueError("expectations is not an array")
    if not all(isinstance(e, dict) for e in exps):
        raise ValueError("expectations contains non-object items")
    bad = [e for e in exps if not isinstance(e.get("passed"), bool)]
    if bad:
        raise ValueError(f"{len(bad)} item(s) have a non-boolean passed (e.g. {bad[0].get('text')!r})")
    got, want = [norm(e.get("text")) for e in exps], [norm(a) for a in asserts]
    if sorted(got) != sorted(want):
        raise ValueError(f"does not match the assertions (graded {len(got)} / expected {len(want)})"
                         f"\n  not graded: {[a for a in want if a not in got]}"
                         f"\n  extra: {[t for t in got if t not in want]}")
    return exps


def exit_code(results: list[tuple], selected: bool) -> int:
    """Exit code. results is [(case_id, passed count, total)]; selected is whether --case was given.

    With --case, judge the selected cases themselves; for a full run, judge the main cases (MAIN).
    If nothing is left to judge, return 1 (do not treat "nothing to judge" as success).
    """
    judged = results if selected else [r for r in results if r[0] in MAIN]
    return 0 if judged and all(o == n for _, o, n in judged) else 1


def run_case(c: dict, run_dir: Path, grade_only: bool, timeout: int) -> tuple[int, int, int, list[str]]:
    """Run one case. Returns (case_id, passed count, total, lines to print). Lines are returned so parallel output does not interleave."""
    log = []
    d = run_dir / f"case-{c['id']}"
    d.mkdir(parents=True, exist_ok=True)
    answer, grading = d / "answer.md", d / "grading.json"
    asserts = c.get("assertions") or c.get("expectations") or []

    if not grade_only:
        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix="wob-eval-") as cwd:
            out = run_claude(EXECUTOR.format(skill=SKILL, prompt=c["prompt"], today=c["today"]),
                             Path(cwd), timeout, TOOLS)
        answer.write_text(out, encoding="utf-8")
        log.append(f"[case {c['id']}] executor {time.time()-t0:.0f}s -> {answer}")

    # Delete the previous grading first. If it were left in place and the grader returned only an explanation
    # without writing, the existence check would pass and the old grading would be tallied as this run's result
    grading.unlink(missing_ok=True)
    run_claude(GRADER.format(answer_path=answer, expected=c.get("expected_output", ""),
                             assertions="\n".join(f"{i+1}. {a}" for i, a in enumerate(asserts)),
                             out_path=grading), d, timeout, GRADER_TOOLS)
    if not grading.exists():
        log.append(f"[case {c['id']}] grading failed: grading.json was not written")
        return c["id"], 0, len(asserts), log
    try:
        exps = read_grading(grading, asserts)
    except (ValueError, json.JSONDecodeError) as e:
        log.append(f"[case {c['id']}] grading failed: {e}")
        return c["id"], 0, len(asserts), log
    g = json.loads(grading.read_text(encoding="utf-8"))
    ok = sum(1 for e in exps if e["passed"])
    # Even if the grader gets the summary wrong, recompute the tally from expectations
    g["summary"] = {"passed": ok, "failed": len(exps) - ok, "total": len(exps),
                    "pass_rate": round(ok / len(exps), 4) if exps else 0.0}
    grading.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    log += [f"    {'PASS' if e['passed'] else 'FAIL'}  {e['text']}" for e in exps]
    log.append(f"[case {c['id']}] {ok}/{len(exps)}")
    return c["id"], ok, len(exps), log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, action="append", help="eval id to run (repeatable; default is all)")
    ap.add_argument("--jobs", type=int, default=1, help="number of cases to run in parallel (default 1 = serial)")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per case")
    ap.add_argument("--grade-only", metavar="RUN_DIR", help="re-grade an existing run directory")
    args = ap.parse_args()

    cases = json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))["evals"]
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    if not cases:
        sys.exit("no matching eval")

    run_dir = Path(args.grade_only).resolve() if args.grade_only else \
        EVALS / "runs" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"run: {run_dir}  cases: {[c['id'] for c in cases]}  jobs: {args.jobs}\n", flush=True)

    def one(c):
        try:
            return run_case(c, run_dir, bool(args.grade_only), args.timeout)
        except Exception as e:  # one case failing (timeout, exit != 0) must not stop the others
            n = len(c.get("assertions") or c.get("expectations") or [])
            return c["id"], 0, n, [f"[case {c['id']}] run failed: {e}"]

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        for cid, ok, n, log in ex.map(one, cases):
            print("\n".join(log) + "\n", flush=True)
            results.append((cid, ok, n))

    tot_ok = sum(r[1] for r in results)
    tot = sum(r[2] for r in results)
    print("=" * 60)
    for cid, ok, n in results:
        print(f"case {cid}: {ok}/{n}" + ("  <- main case" if cid in MAIN else ""))
    print(f"pass_rate {tot_ok}/{tot} = {tot_ok/tot:.1%}" if tot else "pass_rate not measurable")
    (run_dir / "summary.json").write_text(json.dumps(
        {"run": run_dir.name,
         "cases": [{"id": c, "passed": o, "total": n} for c, o, n in results],
         "pass_rate": round(tot_ok / tot, 4) if tot else 0.0}, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(exit_code(results, bool(args.case)))


if __name__ == "__main__":
    main()
