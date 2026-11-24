#!/usr/bin/env python3
"""Flag open issues whose body looks out of step with their title or with the present ("suspects", not verdicts).

Why
---
An agent that picks up an issue reads the body with one `gh issue view` call and nothing else. When only the title
or the comments were updated, the body keeps a dead deadline or an old design, and work piles up on it. Seen in
practice: a title moved on to the next fiscal year and round while the body's heading still named the previous
one, with its closed application window; it was caught only because an agent happened to read it.

What it does
------------
Read-only. It prints suspects for a person or agent to check against the issue, its comments and related PRs before
changing anything. It never edits an issue body: a guessed rewrite of the canonical text is worse than a stale one.

Check A: the title and the body's heading name different fiscal-year or round tokens
    Tokens: 「令和N年度」 (Japanese era fiscal year), 「YYYY年度」 (fiscal year) and 「第N回」 (round N).
    Compared against the body's first non-empty line only (cut to --head-chars), because the observed failure is
    a heading left behind with the old title, while later lines legitimately mention past years ("round 2 of the
    previous year is not pursued"), which a wider window reports as a false positive.
    Fires only when the heading has a value the title lacks, and only for a token kind both sides have.

Check B: a self-declared "as of" date in the body is old
    「YYYY-MM-DD 時点」 or 「YYYY/MM/DD 時点」 ("as of <date>") older than --stale-days (default 60). Old is not
    wrong: on an issue that has not moved, it is normal.

A third check, "the body still has a past deadline", is left out: it also catches historical dates, finished
milestones and quoted past results, so no threshold separates the real cases.

Usage
-----
    stale_body_check.py measure --repos example-org/example-repo [example-org/other-repo ...]
        Runs both checks over each repo's open issues and prints the counts
    stale_body_check.py measure --repos example-org/example-repo --show
        Also prints one line per suspect issue with its reasons (--json for JSON)

Exit status: 0, or 1 when an issue list could not be fetched (so "0 suspects" and "not measured" differ).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys

# Fiscal-year and round tokens, which should agree between the title and the body's heading.
_ERA_YEAR = re.compile(r"令和\s*(\d{1,2})\s*年度")
_SEIREKI_YEAR = re.compile(r"(20\d{2})\s*年度")
_ROUND = re.compile(r"第\s*(\d{1,2})\s*回")
# Self-declared snapshot dates: "(2026-07-16 時点)", "2026/07/16 時点".
_AS_OF = re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\s*時点")

HEAD_CHARS = 1200
AS_OF_STALE_DAYS = 60
# Seconds allowed for one gh issue list call. Measured: 100 issues with bodies in 1.5 s; --limit can grow.
GH_TIMEOUT = 60


def _tokens(text: str) -> dict[str, set[str]]:
    return {
        "era_year": {m.group(1) for m in _ERA_YEAR.finditer(text)},
        "seireki_year": {m.group(1) for m in _SEIREKI_YEAR.finditer(text)},
        "round": {m.group(1) for m in _ROUND.finditer(text)},
    }


def check_token_mismatch(title: str, body: str, head_chars: int = HEAD_CHARS) -> list[str]:
    """Reasons when the body's first non-empty line has a fiscal-year or round value the title lacks.

    A kind missing on either side is not judged (a title that names no year is out of scope). Only "the heading has a
    value the title lacks" fires; the reverse is usually a body that simply does not mention it.
    """
    head = next((ln for ln in body.splitlines() if ln.strip()), "")[:head_chars]
    reasons = []
    for kind, label in (("era_year", "era fiscal year"), ("seireki_year", "fiscal year"), ("round", "round")):
        t_vals = _tokens(title)[kind]
        b_vals = _tokens(head)[kind]
        if not t_vals or not b_vals:
            continue
        extra = b_vals - t_vals
        if extra:
            reasons.append(f"{label}: body heading has {sorted(extra)}, title has {sorted(t_vals)}")
    return reasons


def check_as_of_stale(body: str, today: dt.date, stale_days: int = AS_OF_STALE_DAYS) -> list[str]:
    """Reasons for each "as of" date in the body older than stale_days."""
    reasons = []
    for m in _AS_OF.finditer(body):
        try:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue  # an impossible date such as 2026-13-45 is ignored rather than reported
        age = (today - d).days
        if age > stale_days:
            reasons.append(f"as of {d.isoformat()} is {age} days old")
    return reasons


def fetch_open_issues(repo: str, limit: int) -> list[dict]:
    """number / title / body / updatedAt of the repo's open issues, through gh. A failure raises."""
    try:
        proc = subprocess.run(
            ["gh", "issue", "list", "--repo", repo, "--state", "open",
             "--limit", str(limit), "--json", "number,title,body,updatedAt"],
            capture_output=True, text=True, timeout=GH_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{repo}: gh issue list did not finish in {GH_TIMEOUT} s") from None
    if proc.returncode != 0:
        raise RuntimeError(f"{repo}: gh issue list failed (exit {proc.returncode}): {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout or "[]")


def _nonneg_int(value: str) -> int:
    """Rejects negatives: --stale-days -1 would report every valid past date, and --head-chars -1 would cut the
    heading's last character and miss a token that ends there."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {value!r}") from None
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be 0 or more: {value!r}")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure", help="run the checks and print the counts")
    m.add_argument("--repos", nargs="+", required=True, help="one or more owner/repo")
    m.add_argument("--limit", type=_nonneg_int, default=100, help="most issues read per repo")
    m.add_argument("--head-chars", type=_nonneg_int, default=HEAD_CHARS)
    m.add_argument("--stale-days", type=_nonneg_int, default=AS_OF_STALE_DAYS)
    m.add_argument("--show", action="store_true", help="also print each suspect issue")
    m.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()

    today = dt.date.today()
    scanned = 0
    hits: list[dict] = []
    errors: list[str] = []

    for repo in args.repos:
        try:
            issues = fetch_open_issues(repo, args.limit)
        except RuntimeError as e:
            errors.append(str(e))  # never report a fetch failure as zero issues
            continue
        for it in issues:
            scanned += 1
            title, body = it.get("title") or "", it.get("body") or ""
            reasons = ([f"A: {r}" for r in check_token_mismatch(title, body, args.head_chars)]
                       + [f"B: {r}" for r in check_as_of_stale(body, today, args.stale_days)])
            if reasons:
                hits.append({"repo": repo, "number": it.get("number"), "title": title[:70],
                             "reasons": reasons, "updated_at": it.get("updatedAt")})

    a_hits = sum(1 for h in hits if any(r.startswith("A:") for r in h["reasons"]))
    b_hits = sum(1 for h in hits if any(r.startswith("B:") for r in h["reasons"]))
    result = {"scanned": scanned, "hit_issues": len(hits),
              "check_a_token_mismatch": a_hits, "check_b_as_of_stale": b_hits, "errors": errors}

    if args.json:
        print(json.dumps({**result, "hits": hits if args.show else []}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
        if args.show:
            for h in hits:
                print(f"  {h['repo']}#{h['number']} {h['title']}")
                for r in h["reasons"]:
                    print(f"      {r}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
