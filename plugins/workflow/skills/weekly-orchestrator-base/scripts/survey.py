#!/usr/bin/env python3
"""Gather the situation for planning a cycle, mechanically (no judgment; standard library only, Python 3.9+).

  survey.py                     # read GitHub with gh and print the survey
  survey.py --today YYYY-MM-DD  # plan as if today were that day

Reads only (gh / GraphQL, never the GitHub MCP): open issues with sub-issue summaries and Issue Fields, open PRs,
and the cycle issues. The repos are the config's `repo`, then `extra_repos`, then (when
`repos_from_additional_directories` is true) the GitHub repos behind `.claude/settings.json`
`permissions.additionalDirectories`. With more than one repo every issue is written `owner/repo#N`.

Prints: the cycle (this cycle's issue and its Plan status, where the previous cycle ended), each repo's goals
(children done, open children waiting for a design review, last child update) with their open children, open issues
under no goal, minimum-bar candidates (Start/Target date by the end of the cycle, Priority High/Urgent), open PRs,
what the previous cycle leaves over, and warnings. Clear every warning before planning.
"""
import argparse, datetime as dt, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cycle import (CycleError, anchor_for, boundary, carry_over, cycle_issues, is_confirmed, load_config,  # noqa: E402
                   owner_repo, parse_title, pin_skew, placeholders, plan_status, run, title_for, today as today_in)

ISSUES_QUERY = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
 issues(states:OPEN,first:100){nodes{
 number title updatedAt parent{number parent{number}} subIssuesSummary{total completed}
 subIssues(first:100){nodes{updatedAt}}
 issueFieldValues(first:20){nodes{
  ... on IssueFieldSingleSelectValue{name field{... on IssueFieldSingleSelect{name}}}
  ... on IssueFieldDateValue{value field{... on IssueFieldDate{name}}}}}}}}}"""
PAGE = 100


def main_checkout(root):
    """The main working tree, so a relative additionalDirectories entry resolves the same from a worktree."""
    try:
        common = run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"]).strip()
        return Path(common).parent
    except subprocess.CalledProcessError:
        return Path(root)


def repos(cfg, warn):
    out = [cfg["repo"]] + [r for r in cfg["extra_repos"] if r != cfg["repo"]]
    if not cfg["repos_from_additional_directories"]:
        return out
    settings = cfg["_root"] / ".claude" / "settings.json"
    dirs = []
    if settings.exists():
        dirs = json.loads(settings.read_text(encoding="utf-8")).get("permissions", {}).get("additionalDirectories", [])
    if not dirs:
        warn.append(".claude/settings.json has no permissions.additionalDirectories; read only the configured repos")
    base = main_checkout(cfg["_root"])
    for d in dirs:
        p = Path(d).expanduser()
        p = (p if p.is_absolute() else base / p).resolve()
        if not p.is_dir():
            warn.append(f"additionalDirectories entry {d} does not exist; that repo was not read")
            continue
        try:
            r = owner_repo(run(["git", "-C", str(p), "remote", "get-url", "origin"]))
        except (subprocess.CalledProcessError, CycleError) as e:
            warn.append(f"additionalDirectories entry {d} has no GitHub origin ({e}); not read")
            continue
        if r not in out:
            out.append(r)
    return out


def collect(cfg, warn):
    data = []
    for repo in repos(cfg, warn):
        owner, name = repo.split("/")
        issues = json.loads(run(["gh", "api", "graphql", "-f", f"query={ISSUES_QUERY}",
                                 "-F", f"owner={owner}", "-F", f"name={name}"]))
        prs = json.loads(run(["gh", "pr", "list", "-R", repo, "--state", "open", "--json",
                              "number,title,headRefName,isDraft,reviewDecision,closingIssuesReferences"]))
        data.append({"repo": repo, "issues": issues["data"]["repository"]["issues"]["nodes"], "prs": prs})
    return data


def fields(issue):
    out = {}
    for n in (issue.get("issueFieldValues") or {}).get("nodes", []):
        if n and n.get("field"):
            out[n["field"]["name"]] = n.get("name") or n.get("value")
    return out


def local_date(cfg, ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(cfg["_tz"]).date()


def linked(pr):
    nums = {r["number"] for r in pr.get("closingIssuesReferences") or []}
    # Only the title: the body's #N also matches mentions such as acceptance criteria
    nums |= {int(n) for n in re.findall(r"#(\d+)", pr["title"])}
    return sorted(nums)


def render_repo(cfg, r, today, end, skip, multi, warn):
    F = cfg["fields"]
    repo = r["repo"]
    ref = (lambda n: f"{repo}#{n}") if multi else (lambda n: f"#{n}")
    if len(r["issues"]) >= PAGE:
        warn.append(f"{repo} has {PAGE} or more open issues; the survey reads only the first {PAGE}")
    # Cycle issues are the orchestrator's own, not work (also one the cycle list has not caught up with yet)
    issues = [i for i in r["issues"] if i["number"] not in skip and not parse_title(cfg, i["title"])]
    nums = {i["number"] for i in issues}
    if cfg["goal_marker"]:
        goals = [i for i in issues if cfg["goal_marker"] in i["title"]]
        how = f"title contains {cfg['goal_marker']}"
    else:
        goals = [i for i in issues if not i.get("parent") and (i.get("subIssuesSummary") or {}).get("total")]
        how = "no goal_marker set: top-level open issues with sub-issues"
    goal_nums = {g["number"] for g in goals}

    def goal_of(i):
        p = i.get("parent")
        while p:  # up to two levels: a grandchild still counts when the middle parent is closed
            if p["number"] in goal_nums:
                return p["number"]
            p = p.get("parent")
        return None

    prs_by = {}
    for p in r["prs"]:
        for n in linked(p):
            prs_by.setdefault(n, []).append(p["number"])

    def tag(i):
        f = fields(i)
        t = [f.get(F["priority"], "no " + F["priority"])]
        for k in (F["arch_review"], F["start"], F["target"]):
            if f.get(k):
                t.append(f"{k}: {f[k]}")
        if prs_by.get(i["number"]):
            t.append("PR " + ", ".join(ref(n) for n in prs_by[i["number"]]))
        return ", ".join(t)

    kids = {}
    for i in issues:
        if goal_of(i):
            kids.setdefault(goal_of(i), []).append(i)

    print(f"\n## {repo}")
    print(f"\n### Goals ({how})")
    for g in sorted(goals, key=lambda x: x["number"]):
        s = g["subIssuesSummary"]
        children = kids.get(g["number"], [])
        nodes = (g.get("subIssues") or {}).get("nodes", [])
        if len(nodes) < s["total"]:
            warn.append(f"{ref(g['number'])} has {s['total']} children; the survey read only {len(nodes)}, "
                        "so its last child update may be too old")
        pending = sum(fields(c).get(F["arch_review"]) == "Pending" for c in children)
        stamps = [n["updatedAt"] for n in nodes if n.get("updatedAt")] + [c["updatedAt"] for c in children if c.get("updatedAt")]
        if stamps:
            d = max(local_date(cfg, t) for t in stamps)
            last = f"last child update {d.isoformat()} ({(today - d).days} days ago)"
        else:
            last = "no child updates"
        print(f"- {ref(g['number'])} {g['title']} (children {s['completed']}/{s['total']} done, "
              f"{pending} open children {F['arch_review']}: Pending, {last}; {tag(g)})")
        for c in sorted(children, key=lambda x: x["number"]):
            via = f", via {ref(c['parent']['number'])}" if c["parent"]["number"] != g["number"] else ""
            print(f"  - {ref(c['number'])} {c['title']} ({tag(c)}{via})")
        if not children:
            warn.append(f"{ref(g['number'])} has no open child issue: split the next sub-step, or close the goal")
    if not goals:
        print("- none")

    print("\n### Open issues under no goal (children indented under their open parent)")
    loose = [i for i in issues if i["number"] not in goal_nums and not goal_of(i)]
    loose_nums = {i["number"] for i in loose}
    under = {}
    for i in loose:
        p = i.get("parent")
        if p and p["number"] in loose_nums:
            under.setdefault(p["number"], []).append(i)

    def tree(i, depth, gated):
        p = i.get("parent")
        note = f", parent {ref(p['number'])} is closed" if depth == 0 and p and p["number"] not in nums else ""
        gate = f", parent is {F['arch_review']}: Pending" if gated else ""
        print(f"{'  ' * depth}- {ref(i['number'])} {i['title']} ({tag(i)}{note}{gate})")
        for c in sorted(under.get(i["number"], []), key=lambda x: x["number"]):
            tree(c, depth + 1, gated or fields(i).get(F["arch_review"]) == "Pending")

    for i in sorted(loose, key=lambda x: x["number"]):
        p = i.get("parent")
        if not (p and p["number"] in loose_nums):
            tree(i, 0, False)
    if not loose:
        print("- none")

    print(f"\n### Minimum-bar candidates (by the end of the cycle, {end.isoformat()})")
    print(f"#### {F['start']} or {F['target']} on or before {end.isoformat()}")
    dated = [i for i in issues if any(fields(i).get(k) and dt.date.fromisoformat(fields(i)[k]) <= end
                                      for k in (F["start"], F["target"]))]
    for i in sorted(dated, key=lambda x: x["number"]):
        print(f"- {ref(i['number'])} {i['title']} ({tag(i)})")
    if not dated:
        print("- none")
    print(f"#### {F['priority']} High / Urgent")
    hot = [i for i in issues if fields(i).get(F["priority"]) in ("High", "Urgent")]
    for i in sorted(hot, key=lambda x: x["number"]):
        print(f"- {ref(i['number'])} {i['title']} ({tag(i)})")
    if not hot:
        print("- none")

    print(f"\n### Open PRs (review left: gh pr view <N> -R {repo} --comments)")
    for p in r["prs"]:
        links = ", ".join(ref(n) for n in linked(p)) or "no issue reference"
        rd = p.get("reviewDecision") or "no review decision"
        print(f"- {ref(p['number'])} {p['title']} ({p['headRefName']}{', draft' if p.get('isDraft') else ''}, {rd}, {links})")
    if not r["prs"]:
        print("- none")

    for i in sorted(issues, key=lambda x: x["number"]):
        if fields(i).get(F["arch_review"]) == "Pending":
            warn.append(f"{ref(i['number'])} is {F['arch_review']}: Pending; do not make it an implementation task (defer it with the reason)")


def render(cfg, data, cycles, today, warn):
    anchor = anchor_for(cfg, today)
    v = placeholders(cfg, anchor)
    end = dt.date.fromisoformat(v["end"])
    title = title_for(cfg, anchor)
    multi = len(data) > 1
    me = (lambda n: f"{cfg['repo']}#{n}") if multi else (lambda n: f"#{n}")
    current = [c for c in cycles if c["anchor"] == anchor]
    before = [c for c in cycles if c["anchor"] < anchor]
    opened = [c for c in cycles if c["state"] == "OPEN"]

    print(f"# weekly-orchestrator survey ({today.isoformat()}, {today.strftime('%A')})\n")
    print(f"## Cycle (cycle issues in {cfg['repo']})")
    print(f"- This cycle: {title} ({v['start']} to {v['end']})")
    closed = [c for c in before if c["state"] == "CLOSED"]
    if closed:
        at, src = boundary(cfg, closed[-1])
        print(f"- Previous cycle ended: {me(closed[-1]['number'])} {closed[-1]['title']} at {at} (from: {src}); "
              "this cycle counts from there")
    else:
        print("- Previous cycle ended: no record")
    for c in opened:
        print(f"- Open cycle issue: {me(c['number'])} {c['title']}, Plan status: {plan_status(c.get('body'))}")
    if not cycles:
        warn.append(f"no cycle issue yet (first cycle): nothing to carry over; create {title!r} first "
                    "(cycle.py new, then write it following issue-ops)")
    elif not current:
        warn.append(f"no issue for this cycle ({title!r}): close out the previous cycle and create it (SKILL.md step 5)")
    for c in current:
        if c["state"] == "OPEN" and not is_confirmed(c.get("body")):
            warn.append(f"{me(c['number'])}'s plan section is not confirmed yet ({plan_status(c.get('body'))}): make the plan")
    for c in opened:
        if c["anchor"] < anchor:
            warn.append(f"{me(c['number'])} ({c['title']}) is still open after its cycle; close it out before starting this one")
    if len(opened) > 1:
        warn.append(f"{len(opened)} cycle issues are open; close out the older one")

    skip = {c["number"] for c in cycles}
    for r in data:
        render_repo(cfg, r, today, end, skip if r["repo"] == cfg["repo"] else set(), multi, warn)

    print("\n## Left over from the previous cycle")
    prev = before[-1] if before else None
    if prev:
        items, batches = carry_over(prev.get("body"))
        print(f"- From: {me(prev['number'])} {prev['title']} ({prev['state']})")
        for it in items:
            print(f"- [minimum bar not met] {it}")
        for b in batches:
            print("- [batch not done] " + " / ".join(f"{k}: {x}" for k, x in b.items() if x))
        if not items and not batches:
            print("- none (minimum bar met, every batch done)")
    else:
        print("- No previous cycle issue; nothing to carry over")

    print("\n## Warnings")
    for w in warn or ["none"]:
        print(f"- {w}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", help="path of the config (default: <repo root>/.claude/weekly-orchestrator.json)")
    ap.add_argument("--today", help="plan as if today were this day (YYYY-MM-DD)")
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
        warn = [w for w in [pin_skew(cfg)] if w]
        data = collect(cfg, warn)
        cycles = cycle_issues(cfg)
        day = dt.date.fromisoformat(a.today) if a.today else today_in(cfg)
        render(cfg, data, cycles, day, warn)
    except (CycleError, subprocess.CalledProcessError) as e:
        msg = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
        print(f"survey.py: {msg}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
