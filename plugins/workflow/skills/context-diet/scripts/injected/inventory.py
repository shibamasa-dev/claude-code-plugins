#!/usr/bin/env python3
"""注入層（MCP コネクタ・skills）の棚卸し。収集のみ — 要否の判定はしない。

判定を機械に持たせないのは意図的。「このプロジェクトで何が要るか」は
プロジェクトの中身とユーザーの意図を読まないと決まらない。
このスクリプトは「候補と、それぞれが何バイト食っているか」だけを出す。

  python3 inventory.py [--project PATH] [--no-connectors]

出力: JSON（stdout）
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
# "name: url-or-command - status" 形式の1行
MCP_LINE_RE = re.compile(r"^(?P<name>.+?):\s+(?P<target>.*?)\s+-\s+(?P<status>.+)$")


def description_bytes(skill_dir: Path) -> tuple[int, str]:
    """SKILL.md の description の長さと先頭を返す。読めなければ (0, "")。"""
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
    """enabledPlugins に載っているプラグインの skills だけを列挙する。"""
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
    """`claude mcp list` を叩く。ヘルスチェックが走るので数秒〜数十秒かかる。"""
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
    ap.add_argument("--home", default=None, help="疑似 HOME（evals 用）")
    ap.add_argument("--no-connectors", action="store_true",
                    help="claude mcp list を叩かない（オフライン・高速）")
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
            "アカウント側スキル（small-business:* / anthropic-skills:* / design:* 等）は "
            "ディスク上に無く、ここには出ない。エージェント自身の skills 一覧から読むこと。",
            "組み込みスキル（code-review / simplify / schedule 等）も同様にここには出ない。",
        ],
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
