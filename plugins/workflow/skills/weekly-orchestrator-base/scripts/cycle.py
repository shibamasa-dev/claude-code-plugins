#!/usr/bin/env python3
"""The cycle issue's title, week and body, computed in one place (standard library only, Python 3.9+).

The orchestrator skill and the weekly-issue GitHub Actions workflow both call this script, so the title of a
cycle is computed once. Nothing here writes to GitHub: the skill writes following issue-ops, the workflow
creates the issue with `gh issue create`. Every subcommand prints to stdout.

  cycle.py resolve [--date YYYY-MM-DD | --now ISO]   # the cycle containing that day (default: now, in the config's timezone)
  cycle.py new [--date D | --now ISO]               # title and body of that cycle's issue, no carry-over
  cycle.py new --prev prev.json                     # the cycle a week after a closed one, carrying its unchecked minimum bar
  cycle.py new ... --into cur.json                  # splice only the plan section into an existing issue's body (Draft only)
  cycle.py exists --title T                         # is there an issue with exactly this title (open or closed)?
  cycle.py boundary prev.json                       # where the next cycle starts counting (tally start -> boundary -> close)
  cycle.py refs <file>                              # bare #N references (exit 1 when found)
  cycle.py cron --weekday monday --hour 7 [--minute 17]   # the workflow's UTC cron line for a local time

prev.json / cur.json are `gh issue view <n> -R <owner/repo> --json title,body[,closedAt]`.
The repo's differences come from .claude/weekly-orchestrator.json (see references/config.md); without the file
the base defaults apply (a Monday-to-Sunday week titled `Orchestrator: <repo> <YYYY>-W<ww>`, boundary `Cutoff`, UTC).
"""
import argparse, datetime as dt, json, os, re, subprocess, sys
from pathlib import Path

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover - Python < 3.9
    sys.exit("cycle.py needs Python 3.9 or later (zoneinfo)")

SKILL = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL / "references" / "plan-section.md"
CONFIG_PATH = Path(".claude") / "weekly-orchestrator.json"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

DEFAULTS = {
    "repo": "",                      # owner/name; empty: $GITHUB_REPOSITORY, then `git remote get-url origin`
    "title": "Orchestrator: {repo_name} {iso_week}",
    "legacy_titles": [],             # older title formats still read as cycle issues
    "anchor_weekday": "monday",      # weekday of the date the title carries
    "lead_days": 0,                  # days before that date that already belong to its cycle
    "timezone": "UTC",               # IANA name; both the skill and the workflow compute dates in it
    "period": "{start} to {end}",    # fills {period} in the plan section heading
    "boundary": "Cutoff",            # first line of ## Result: Cutoff or Submitted
    "goal_marker": "",               # title substring of goal issues; empty: top-level issues with sub-issues
    "plan_extra": "",                # repo file inserted in the plan section after the Plan status line
    "footer": "",                    # repo file appended after the plan section
    "extra_repos": [],               # more owner/name repos the survey reads
    "repos_from_additional_directories": False,  # also read the repos behind .claude/settings.json additionalDirectories
    "fields": {"priority": "Priority", "arch_review": "Arch Review",
               "start": "Start date", "target": "Target date"},
    "issue_fields": [],              # values the workflow sets on a new issue (best effort)
}

PLAN_BLOCK = re.compile(r"^<!-- weekly-orchestrator:plan -->$.*?^<!-- /weekly-orchestrator:plan -->$", re.M | re.S)
# Older cycle issues and project templates may be in Japanese; these read both
STATUS_LINE = re.compile(r"\*\*(?:Plan status|計画の状態)\*\*[:：]\s*([^\n]+)")
CONFIRMED = ("Confirmed", "確定")
DRAFT = ("Draft", "未確定")
RESULT_HEAD = re.compile(r"^## (?:Result|結果|Notes for next time|次回への引き継ぎ)\s*$", re.M)
RESULT_TAIL = re.compile(r"^## (?:Result|結果)\s*$", re.M)
TALLY = ("Tally start", "集計起点")
BOUNDARY = ("Cutoff", "Submitted", "締め", "提出")
MIN_BAR = ("Minimum bar", "最低ライン")
BATCHES = ("Batches", "バッチ")
STATUS_COL = ("Status", "状態")
DONE = ("Done", "完了")
CARRY = "(carried over) "
OLD_CARRY = ("（持ち越し候補）",)
BARE_REF = re.compile(r"(?<![\w/#&])#(\d+)\b")


class CycleError(Exception):
    pass


def run(cmd, cwd=None):
    return subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", cwd=cwd).stdout


# ---------- config ----------

def repo_root(start="."):
    try:
        return Path(run(["git", "rev-parse", "--show-toplevel"], cwd=start).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(start).resolve()


def owner_repo(url):
    """owner/name from a GitHub remote URL (https or ssh)."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        raise CycleError(f"not a GitHub URL: {url.strip()}")
    return f"{m.group(1)}/{m.group(2)}"


def load_config(path=None, root=None):
    root = Path(root) if root else repo_root()
    if path and not Path(path).exists():
        # The defaults would compute another title; a path given on purpose must exist
        raise CycleError(f"config not found: {path}")
    p = Path(path) if path else root / CONFIG_PATH
    cfg = json.loads(json.dumps(DEFAULTS))
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        unknown = set(data) - set(DEFAULTS) - {"$comment"}
        if unknown:
            raise CycleError(f"{p}: unknown keys {sorted(unknown)} (see references/config.md)")
        if "fields" in data:
            cfg["fields"].update(data.pop("fields"))
        cfg.update(data)
    cfg["_root"], cfg["_path"] = root, p if p.exists() else None
    if not cfg["repo"]:
        cfg["repo"] = os.environ.get("GITHUB_REPOSITORY", "")
    if not cfg["repo"]:
        try:
            cfg["repo"] = owner_repo(run(["git", "-C", str(root), "remote", "get-url", "origin"]))
        except (subprocess.CalledProcessError, FileNotFoundError, CycleError):
            raise CycleError("no repo: set \"repo\" in .claude/weekly-orchestrator.json or add an origin remote")
    if cfg["anchor_weekday"] not in WEEKDAYS:
        raise CycleError(f"anchor_weekday must be one of {WEEKDAYS}")
    if not 0 <= int(cfg["lead_days"]) <= 6:
        raise CycleError("lead_days must be 0 to 6")
    if cfg["boundary"] not in ("Cutoff", "Submitted"):
        raise CycleError("boundary must be Cutoff or Submitted")
    if "{date}" not in cfg["title"] and "{iso_week}" not in cfg["title"]:
        raise CycleError("title must contain {date} or {iso_week}")
    try:
        cfg["_tz"] = ZoneInfo(cfg["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        # Falling back to another zone would shift the date by a day without anyone noticing
        raise CycleError(f"timezone {cfg['timezone']!r} cannot be resolved (is tzdata installed?)")
    return cfg


# ---------- dates and titles ----------

def today(cfg, now=None):
    t = dt.datetime.fromisoformat(now.replace("Z", "+00:00")) if now else dt.datetime.now(dt.timezone.utc)
    if t.tzinfo is None:
        raise CycleError("--now needs a UTC offset (e.g. 2026-11-23T22:17:00Z)")
    return t.astimezone(cfg["_tz"]).date()


def anchor_for(cfg, day):
    """The title date of the cycle containing `day`: the anchor weekday A with A - lead <= day < A - lead + 7."""
    x = day + dt.timedelta(days=int(cfg["lead_days"]))
    return x - dt.timedelta(days=(x.weekday() - WEEKDAYS.index(cfg["anchor_weekday"])) % 7)


def placeholders(cfg, anchor):
    start = anchor - dt.timedelta(days=int(cfg["lead_days"]))
    y, w, _ = anchor.isocalendar()
    return {"date": anchor.isoformat(), "start": start.isoformat(),
            "end": (start + dt.timedelta(days=6)).isoformat(),
            "next": (anchor + dt.timedelta(days=7)).isoformat(),
            "iso_week": f"{y}-W{w:02d}", "repo_name": cfg["repo"].split("/")[-1], "repo": cfg["repo"]}


def fill(text, values):
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    return text


def title_for(cfg, anchor):
    return fill(cfg["title"], placeholders(cfg, anchor))


def _title_pattern(fmt, cfg):
    parts = re.split(r"(\{date\}|\{iso_week\}|\{repo_name\})", fmt)
    out = []
    for p in parts:
        if p == "{date}":
            out.append(r"(?P<date>\d{4}-\d{2}-\d{2})")
        elif p == "{iso_week}":
            out.append(r"(?P<y>\d{4})-W(?P<w>\d{2})")
        elif p == "{repo_name}":
            out.append(re.escape(cfg["repo"].split("/")[-1]))
        else:
            out.append(re.escape(p))
    return re.compile("".join(out))


def parse_title(cfg, title):
    """The anchor date a cycle issue's title carries, or None when the title is not a cycle issue's."""
    for fmt in [cfg["title"]] + list(cfg["legacy_titles"]):
        m = _title_pattern(fmt, cfg).fullmatch(title.strip())
        if not m:
            continue
        if m.groupdict().get("date"):
            return dt.date.fromisoformat(m.group("date"))
        return dt.date.fromisocalendar(int(m.group("y")), int(m.group("w")),
                                       WEEKDAYS.index(cfg["anchor_weekday"]) + 1)
    return None


# ---------- body ----------

def plan_section(body):
    m = PLAN_BLOCK.search(body or "")
    return m.group() if m else ""


def plan_status(body):
    sec = plan_section(body)
    if not sec:
        return "no plan section"
    m = STATUS_LINE.search(sec)
    return m.group(1).strip() if m else "unknown (no Plan status line)"


def is_confirmed(body):
    return plan_status(body).startswith(CONFIRMED)


def subsection(sec, heads):
    for head in heads:
        m = re.search(r"^### " + re.escape(head) + r"[^\n]*\n(.*?)(?=^### |^<!-- /weekly|\Z)", sec, flags=re.M | re.S)
        if m:
            return m.group(1)
    return ""


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def carry_over(body):
    """(unchecked minimum-bar items, batch rows whose Status is not Done) from a cycle issue's plan section.

    Anything after `## Result` (added at close) is not read.
    """
    sec = plan_section(RESULT_HEAD.split(body or "", maxsplit=1)[0])
    items = []
    for line in subsection(sec, MIN_BAR).splitlines():
        s = line.strip()
        if s.startswith("- [ ]") and s[len("- [ ]"):].strip():
            text = s[len("- [ ]"):].strip()
            for mark in (CARRY.strip(),) + OLD_CARRY:
                if text.startswith(mark):
                    text = text[len(mark):].strip()
            items.append(text)
    rows = [l for l in subsection(sec, BATCHES).splitlines() if l.strip().startswith("|")]
    batches = []
    if len(rows) > 2:
        head = _cells(rows[0])
        idx = next((head.index(c) for c in STATUS_COL if c in head), None)
        for line in rows[2:]:
            cells = _cells(line)
            if idx is not None and idx < len(cells) and not cells[idx].startswith(DONE):
                batches.append(dict(zip(head, cells)))
    return items, batches


def _repo_file(cfg, key):
    if not cfg[key]:
        return ""
    p = Path(cfg[key])
    p = p if p.is_absolute() else cfg["_root"] / p
    if not p.exists():
        raise CycleError(f"{key} file not found: {cfg[key]}")
    return p.read_text(encoding="utf-8").strip("\n")


def template():
    text = TEMPLATE.read_text(encoding="utf-8")
    m = PLAN_BLOCK.search(text)
    if not m:
        raise CycleError(f"{TEMPLATE} has no plan section")
    return m.group()


def build(cfg, anchor, carried=()):
    """{title, date, body}: the base template's plan section (plus the repo's extras), then the footer."""
    values = placeholders(cfg, anchor)
    values["period"] = fill(cfg["period"], values)
    sec = fill(template(), values)
    extra = fill(_repo_file(cfg, "plan_extra"), values)
    if extra:
        m = STATUS_LINE.search(sec)
        end = sec.index("\n", m.end()) + 1
        sec = sec[:end] + "\n" + extra + "\n" + sec[end:]
    if carried:
        lines = "".join(f"- [ ] {CARRY}{c}\n" for c in carried)
        sec = sec.replace("- [ ] \n", lines, 1)
    footer = fill(_repo_file(cfg, "footer"), values)
    body = sec + "\n" + ("\n" + footer + "\n" if footer else "")
    return {"title": fill(cfg["title"], values), "date": values["date"], "body": body,
            "issue_fields": issue_fields(cfg, values)}


def issue_fields(cfg, values):
    out = []
    for f in cfg["issue_fields"]:
        f = dict(f)
        if "dateValue" in f:
            f["dateValue"] = fill(f["dateValue"], values)
        out.append(f)
    return out


def splice(new, existing):
    """`existing` with only its plan section replaced by `new`'s. Refuses a confirmed plan, another title,
    or a body without a plan section."""
    if existing["title"].strip() != new["title"]:
        raise CycleError(f"title differs: {existing['title']!r} != {new['title']!r}")
    cur = PLAN_BLOCK.search(existing.get("body") or "")
    if not cur:
        raise CycleError("the existing body has no plan section (ask the user where to put it)")
    if not plan_status(existing["body"]).startswith(DRAFT):
        # Confirmed means someone wrote the plan; no status line means it cannot be told apart from a filled one
        raise CycleError(f"the existing plan section is not a Draft (Plan status: {plan_status(existing['body'])}); "
                         "do not overwrite it, ask the user")
    b = existing["body"]
    out = dict(new)
    out["body"] = b[:cur.start()] + plan_section(new["body"]) + b[cur.end():]
    return out


def boundary(cfg, issue):
    """(ISO time, source) where the next cycle starts counting: Tally start -> Cutoff/Submitted -> close time.

    Lines are read only after `## Result`, and only when they carry a time; they are in the config's timezone.
    """
    body = issue.get("body") or ""
    parts = RESULT_TAIL.split(body, maxsplit=1)
    tail = parts[1] if len(parts) > 1 else ""
    for labels in (TALLY, BOUNDARY):
        for label in labels:
            m = re.search(r"\*\*" + re.escape(label) + r"\*\*[:：]\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", tail)
            if m:
                t = dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}").replace(tzinfo=cfg["_tz"])
                return t.isoformat(), f"## Result {label} line"
    if issue.get("closedAt"):
        return issue["closedAt"], "close time (no boundary line)"
    return None, "none (no boundary line and not closed)"


# ---------- GitHub (read only) ----------

def cycle_issues(cfg, limit=200):
    """Every issue (open or closed) whose title parses as a cycle issue's, newest anchor last.

    Uses the issue list, not the search API: the search index lags and can miss an issue created a moment ago.
    """
    issues = json.loads(run(["gh", "issue", "list", "-R", cfg["repo"], "--state", "all", "--limit", str(limit),
                             "--json", "number,title,state,closedAt,body"]))
    out = [dict(i, anchor=parse_title(cfg, i["title"])) for i in issues]
    return sorted([i for i in out if i["anchor"]], key=lambda i: (i["anchor"], i["number"]))


def exists(cfg, title, limit=200):
    issues = json.loads(run(["gh", "issue", "list", "-R", cfg["repo"], "--state", "all", "--limit", str(limit),
                             "--json", "number,title,state"]))
    return [i for i in issues if i["title"] == title]


# ---------- version skew ----------

PLUGIN_JSON = SKILL.parent.parent / ".claude-plugin" / "plugin.json"
# The last release that changed how a title, week or body is computed. A workflow pinned to it or later computes
# what this copy computes, so only an older pin is a skew worth a warning (not every plugin release)
COMPUTE_VERSION = "0.13.0"
PIN = re.compile(r"^\s*ref:\s*['\"]?workflow--v([0-9][^\s'\"]*)", re.M)


def pin_skew(cfg):
    """A warning when the repo's workflow runs these scripts at another release than this copy, else None.

    The workflow pins the scripts with `ref: workflow--v<version>`; a different copy may compute other titles.
    """
    wf = cfg["_root"] / ".github" / "workflows"
    if not PLUGIN_JSON.exists() or not wf.is_dir():
        return None
    mine = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
    for f in sorted(wf.glob("*.y*ml")):
        for v in PIN.findall(f.read_text(encoding="utf-8")):
            if _ver(v) < _ver(COMPUTE_VERSION):
                return (f"{f.relative_to(cfg['_root'])} runs the scripts of workflow {v}, older than {COMPUTE_VERSION} "
                        f"(the last change to how titles and weeks are computed): set its ref to workflow--v{mine}")
    return None


def _ver(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


# ---------- cron ----------

def cron(cfg, weekday, hour, minute):
    """`M H * * D` in UTC for a local weekday and time, at today's UTC offset (a DST zone shifts it twice a year)."""
    wd = WEEKDAYS.index(weekday)
    base = dt.datetime.now(cfg["_tz"]).date()
    day = base + dt.timedelta(days=(wd - base.weekday()) % 7)
    utc = dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=cfg["_tz"]).astimezone(dt.timezone.utc)
    return f"{utc.minute} {utc.hour} * * {(utc.weekday() + 1) % 7}"


# ---------- CLI ----------

def _read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _day(cfg, a):
    return dt.date.fromisoformat(a.date) if a.date else today(cfg, a.now)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", help="path of the config (default: <repo root>/.claude/weekly-orchestrator.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("resolve", "new"):
        p = sub.add_parser(name)
        p.add_argument("--date", help="a day in the cycle (YYYY-MM-DD, in the config's timezone)")
        p.add_argument("--now", help="an instant (ISO 8601 with offset) instead of the current time")
        if name == "new":
            p.add_argument("--prev", help="the closed cycle issue (JSON); builds the cycle after it with carry-over")
            p.add_argument("--into", help="the existing issue for that cycle (JSON); replace only its plan section")
    p = sub.add_parser("exists"); p.add_argument("--title", required=True)
    p = sub.add_parser("boundary"); p.add_argument("issue")
    p = sub.add_parser("refs"); p.add_argument("file")
    p = sub.add_parser("cron")
    p.add_argument("--weekday", required=True, choices=WEEKDAYS)
    p.add_argument("--hour", type=int, required=True)
    p.add_argument("--minute", type=int, default=17, help="minute of the hour (default 17: off the top of the hour, when Actions is busiest)")
    a = ap.parse_args(argv)

    if a.cmd == "refs":  # needs no config
        hits = [(n, l) for n, l in enumerate(Path(a.file).read_text(encoding="utf-8").splitlines(), 1) if BARE_REF.search(l)]
        for n, l in hits:
            print(f"{n}: {l.strip()}")
        if hits:
            print(f"{len(hits)} line(s) with a bare #N; write owner/repo#N before writing the body", file=sys.stderr)
        return 1 if hits else 0
    try:
        cfg = load_config(a.config)
        if a.cmd == "resolve":
            anchor = anchor_for(cfg, _day(cfg, a))
            out = placeholders(cfg, anchor)
            out["title"] = title_for(cfg, anchor)
            print(json.dumps(out, ensure_ascii=False, indent=1))
        elif a.cmd == "new":
            if a.prev and (a.date or a.now):
                raise CycleError("give --prev or --date/--now, not both")
            if a.prev:
                prev = _read_json(a.prev)
                anchor = parse_title(cfg, prev["title"])
                if not anchor:
                    raise CycleError(f"not a cycle issue title: {prev['title']!r}")
                items, _ = carry_over(prev.get("body"))
                # Resolved like any other day, so a previous title off the anchor weekday still gives the title the
                # workflow computes for that week (two different titles for one cycle meant duplicate issues)
                out = build(cfg, anchor_for(cfg, anchor + dt.timedelta(days=7)), items)
            else:
                out = build(cfg, anchor_for(cfg, _day(cfg, a)))
            if a.into:
                out = splice(out, _read_json(a.into))
            print(json.dumps(out, ensure_ascii=False, indent=1))
        elif a.cmd == "exists":
            hits = exists(cfg, a.title)
            print(json.dumps({"exists": bool(hits), "issues": hits}, ensure_ascii=False))
        elif a.cmd == "boundary":
            at, src = boundary(cfg, _read_json(a.issue))
            print(json.dumps({"at": at, "source": src}, ensure_ascii=False))
        elif a.cmd == "cron":
            print(cron(cfg, a.weekday, a.hour, a.minute))
    except (CycleError, subprocess.CalledProcessError, json.JSONDecodeError, OSError) as e:
        msg = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
        print(f"cycle.py {a.cmd}: {msg}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
