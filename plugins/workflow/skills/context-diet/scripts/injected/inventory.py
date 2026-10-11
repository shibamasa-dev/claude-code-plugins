#!/usr/bin/env python3
"""Inventory of the injected layer (MCP connectors, skills). Collection only — no keep/drop decisions.

Keeping the decision out of the machine is deliberate. "What this project needs" can't be
decided without reading the project's contents and the user's intent.
This script only outputs "the candidates, and how many bytes each one takes".

  python3 inventory.py [--project PATH] [--no-connectors]

Output: JSON (stdout)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
DESC_RE = re.compile(r"^description:\s*(.*?)(?=\n\w+:|\Z)", re.S | re.M)
FM_RE = re.compile(r"\A---\n(.*?)\n---", re.S)
# one line in the form "name: url-or-command - status"
MCP_LINE_RE = re.compile(r"^(?P<name>.+?):\s+(?P<target>.*?)\s+-\s+(?P<status>.+)$")


def description_bytes(skill_dir: Path) -> tuple[int, str]:
    """Return the length and head of the SKILL.md description. (0, "") if unreadable."""
    try:
        body = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, ""
    fm = FM_RE.search(body)
    if not fm:
        return 0, ""
    m = DESC_RE.search(fm.group(1))
    if not m:
        return 0, ""
    desc = " ".join(m.group(1).split())
    return len(desc.encode("utf-8")), desc[:80]


def personal_skills(home: Path) -> list[dict]:
    root = home / ".claude" / "skills"
    out = []
    if not root.is_dir():
        return out
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or not (entry.is_dir() or entry.is_symlink()):
            continue
        n, head = description_bytes(entry)
        out.append({
            "name": entry.name,
            "source": "personal",
            "real_path": str(entry.resolve()),
            "desc_bytes": n,
            "desc_head": head,
        })
    return out


def enabled_plugin_skills(home: Path) -> list[dict]:
    """List skills only from plugins listed in enabledPlugins."""
    settings = home / ".claude" / "settings.json"
    try:
        enabled = json.loads(settings.read_text(encoding="utf-8")).get("enabledPlugins", {})
    except (OSError, json.JSONDecodeError):
        return []

    mroot = home / ".claude" / "plugins" / "marketplaces"
    out = []
    for key, on in enabled.items():
        if not on or "@" not in key:
            continue
        plugin, _, marketplace = key.partition("@")
        for base in (mroot / marketplace / "plugins" / plugin / "skills",
                     mroot / marketplace / plugin / "skills"):
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                n, head = description_bytes(entry)
                out.append({
                    "name": f"{plugin}:{entry.name}",
                    "source": f"plugin:{marketplace}",
                    "real_path": str(entry),
                    "desc_bytes": n,
                    "desc_head": head,
                })
            break
    return out


def connectors(timeout: int) -> dict:
    """Run `claude mcp list`. Health checks run, so it takes a few seconds to tens of seconds."""
    try:
        p = subprocess.run(["claude", "mcp", "list"], capture_output=True,
                           text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": f"{type(e).__name__}: {e}", "items": []}

    items = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("Checking", "Warning:")):
            continue
        m = MCP_LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name")
        items.append({
            "name": name,
            "target": m.group("target"),
            "status": m.group("status"),
            "kind": "claude.ai connector" if name.startswith("claude.ai ") else "local",
        })
    return {"error": None, "items": items}


def current_settings(project: Path) -> dict:
    p = project / ".claude" / "settings.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    return {
        "path": str(p),
        "exists": p.exists(),
        "deniedMcpServers": [e.get("serverName") for e in d.get("deniedMcpServers", [])
                             if isinstance(e, dict)],
        "skillOverrides": d.get("skillOverrides", {}),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--home", default=None, help="fake HOME (for evals)")
    ap.add_argument("--no-connectors", action="store_true",
                    help="don't run claude mcp list (offline, fast)")
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    home = Path(args.home).resolve() if args.home else HOME
    cur = current_settings(project)
    denied = set(cur["deniedMcpServers"])
    overridden = cur["skillOverrides"]

    conn = {"error": "skipped", "items": []} if args.no_connectors else connectors(args.timeout)
    for c in conn["items"]:
        c["already_denied"] = c["name"] in denied

    skills = personal_skills(home) + enabled_plugin_skills(home)
    for s in skills:
        s["already_overridden"] = overridden.get(s["name"])

    live = [s for s in skills if not s["already_overridden"]]
    report = {
        "project": str(project),
        "settings": cur,
        "connectors": conn,
        "skills": skills,
        "totals": {
            "connectors_listed": len(conn["items"]),
            "connectors_already_denied": sum(1 for c in conn["items"] if c["already_denied"]),
            "skills_found": len(skills),
            "skills_already_overridden": len(skills) - len(live),
            "live_desc_bytes": sum(s["desc_bytes"] for s in live),
        },
        "not_enumerable": [
            "Account-side skills (small-business:* / anthropic-skills:* / design:*, etc.) are "
            "not on disk and don't appear here. Read them from the agent's own skills list.",
            "Built-in skills (code-review / simplify / schedule, etc.) don't appear here either.",
        ],
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
