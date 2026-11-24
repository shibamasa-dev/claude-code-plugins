#!/usr/bin/env python3
"""Place a repo's orchestrator files from the config (standard library only, Python 3.9+).

  scaffold.py --skill-name <name> [--run-weekday monday] [--hour 7] [--minute 17] [--notes AGENTS.md] [--dry-run]

Run from the repo's root after writing .claude/weekly-orchestrator.json. It validates the config with the base
skill's cycle.py, then writes, at fixed paths, the files the repo commits:

  .claude/skills/<name>/SKILL.md            the project skill template ("read and follow weekly-orchestrator-base")
  .github/workflows/weekly-cycle-issue.yml  the weekly-issue workflow, cron computed from the config's timezone
  AGENTS.md (or --notes)                    a three-line "Weekly plan" section appended

It never overwrites: an existing skill or workflow file stops it before anything is written, and a notes file that
already has a "## Weekly plan" heading is left alone. --dry-run prints what it would write. Last, it prints this
cycle's title as cycle.py resolves it, so the result can be checked by eye.
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
BASE = SKILL.parent / "weekly-orchestrator-base"
sys.path.insert(0, str(BASE / "scripts"))
from cycle import CycleError, WEEKDAYS, anchor_for, cron, load_config, title_for, today  # noqa: E402

PLUGIN_JSON = SKILL.parent.parent / ".claude-plugin" / "plugin.json"


def render(name, values):
    text = (SKILL / "assets" / name).read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace(f"__{k}__", v)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--skill-name", required=True, help="the project skill's name, e.g. sample-weekly")
    ap.add_argument("--run-weekday", choices=WEEKDAYS, help="local weekday the workflow runs (default: the config's anchor_weekday)")
    ap.add_argument("--hour", type=int, default=7, help="local hour the workflow runs (default 7)")
    ap.add_argument("--minute", type=int, default=17, help="minute of the hour (default 17)")
    ap.add_argument("--notes", default="AGENTS.md", help="file that gets the Weekly plan section (default AGENTS.md)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        cfg = load_config()
    except CycleError as e:
        sys.exit(f"scaffold.py: {e}")
    if cfg["_path"] is None:
        sys.exit("scaffold.py: write .claude/weekly-orchestrator.json first (keys in weekly-orchestrator-base references/config.md)")
    root = cfg["_root"]
    version = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]
    weekday = a.run_weekday or cfg["anchor_weekday"]
    values = {"SKILL_NAME": a.skill_name, "REPO": cfg["repo"], "REPO_NAME": cfg["repo"].split("/")[-1],
              "TITLE_FORMAT": cfg["title"], "KIT_REF": f"workflow--v{version}",
              "CRON": cron(cfg, weekday, a.hour, a.minute),
              "RUN_AT": f"{weekday.capitalize()} {a.hour:02d}:{a.minute:02d} {cfg['timezone']}"}
    files = [(root / ".claude" / "skills" / a.skill_name / "SKILL.md", render("project-skill.md", values)),
             (root / ".github" / "workflows" / "weekly-cycle-issue.yml", render("weekly-cycle-issue.yml", values))]
    taken = [str(p.relative_to(root)) for p, _ in files if p.exists()]
    if taken:
        sys.exit(f"scaffold.py: already exists, not overwriting: {', '.join(taken)}")
    notes = root / a.notes
    section = render("agents-section.md", values)
    has_section = notes.exists() and "\n## Weekly plan" in "\n" + notes.read_text(encoding="utf-8")

    for p, text in files:
        print(f"{'would write' if a.dry_run else 'wrote'} {p.relative_to(root)}")
        if not a.dry_run:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
    if has_section:
        print(f"left {a.notes} alone (it already has a ## Weekly plan section)")
    else:
        print(f"{'would append' if a.dry_run else 'appended'} the Weekly plan section to {a.notes}")
        if not a.dry_run:
            with notes.open("a", encoding="utf-8") as f:
                f.write(section)
    print(f"cron: {values['CRON']} (UTC) = {values['RUN_AT']}")
    print(f"this cycle: {title_for(cfg, anchor_for(cfg, today(cfg)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
