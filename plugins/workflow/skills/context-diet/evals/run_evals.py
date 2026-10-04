#!/usr/bin/env python3
"""context-diet evals: フィクスチャを $TMPDIR に自動生成して measure.py を3ケース検証。

手作業ゼロ。evals.json がケース定義（期待 verdict・期待 breach 部分文字列）。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEASURE = HERE.parent / "scripts" / "standing" / "measure.py"
INVENTORY = HERE.parent / "scripts" / "injected" / "inventory.py"


def skill_md(dirpath: Path, name: str, desc: str) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n")


def build_inventory_fixture(root: Path, kind: str) -> tuple:
    """疑似 HOME/プロジェクトを作る。戻り値 (home, project)。"""
    home = root / "home"
    project = root / "proj"
    (project / ".claude").mkdir(parents=True)

    skills = home / ".claude" / "skills"
    skill_md(skills / "keeper", "keeper", "残す想定のスキル")
    skill_md(skills / "dropme", "dropme", "落とす想定のスキル。説明文はそこそこ長い。")

    mkt = home / ".claude" / "plugins" / "marketplaces"
    skill_md(mkt / "mp" / "plugins" / "demo" / "skills" / "helper", "helper", "プラグイン由来")
    # enabledPlugins に載っていないプラグインは列挙されない、の対照
    skill_md(mkt / "mp" / "plugins" / "ghost" / "skills" / "helper", "helper", "無効プラグイン")
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {"demo@mp": True, "ghost@mp": False}}))

    if kind == "configured":
        (project / ".claude" / "settings.json").write_text(json.dumps({
            "hooks": {"SessionStart": []},
            "deniedMcpServers": [{"serverName": "claude.ai Notion"}],
            "skillOverrides": {"dropme": "user-invocable-only", "demo:helper": "off"},
        }))
    elif kind == "fresh":
        (project / ".claude" / "settings.json").write_text(json.dumps({"hooks": {}}))
    # no_settings: .claude/settings.json を作らない
    return home, project


def run_inventory_case(case: dict) -> tuple:
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as td:
        home, project = build_inventory_fixture(Path(td).resolve(), case["fixture"])
        r = subprocess.run(
            [sys.executable, str(INVENTORY), "--project", str(project),
             "--home", str(home), "--no-connectors"],
            capture_output=True, text=True,
        )
        try:
            out = json.loads(r.stdout)
        except json.JSONDecodeError:
            return False, f"JSON parse 失敗: {r.stdout[:120]!r} / stderr {r.stderr[:160]!r}"

        errs = []
        names = [s["name"] for s in out.get("skills", [])]
        for want in case.get("expect_skill_names", []):
            if want not in names:
                errs.append(f"{want!r} が skills に無い: {names}")
        for unwanted in case.get("expect_absent_skill_names", []):
            if unwanted in names:
                errs.append(f"{unwanted!r} が列挙されている（無効プラグインのはず）")
        for k, v in case.get("expect_totals", {}).items():
            if out.get("totals", {}).get(k) != v:
                errs.append(f"totals.{k} {out.get('totals', {}).get(k)} != {v}")
        if "expect_denied" in case:
            got = out.get("settings", {}).get("deniedMcpServers", [])
            if got != case["expect_denied"]:
                errs.append(f"deniedMcpServers {got} != {case['expect_denied']}")
        for k, v in case.get("expect_overridden", {}).items():
            got = next((s["already_overridden"] for s in out["skills"] if s["name"] == k), None)
            if got != v:
                errs.append(f"{k} の already_overridden {got!r} != {v!r}")
        if "expect_settings_exists" in case:
            got = out.get("settings", {}).get("exists")
            if got != case["expect_settings_exists"]:
                errs.append(f"settings.exists {got} != {case['expect_settings_exists']}")
        if "expect_live_desc_bytes_gt" in case:
            got = out.get("totals", {}).get("live_desc_bytes", 0)
            if not got > case["expect_live_desc_bytes_gt"]:
                errs.append(f"live_desc_bytes {got} が {case['expect_live_desc_bytes_gt']} 以下")
        return (not errs), "; ".join(errs)


def build_fixture(root: Path, kind: str) -> tuple:
    """疑似 HOME/プロジェクトを作る。戻り値 (home, project)。"""
    home = root / "home"
    project = root / "proj"
    (home / ".claude" / "rules").mkdir(parents=True)
    project.mkdir(parents=True)
    mem = home / ".claude" / "projects" / str(project).replace("/", "-").replace("_", "-") / "memory"
    mem.mkdir(parents=True)

    (home / ".claude" / "CLAUDE.md").write_text("# global\nルール本文\n" * 20)
    (project / "CLAUDE.md").write_text("@AGENTS.md\n")
    (project / "AGENTS.md").write_text("# agents\n")
    (home / ".claude" / "rules" / "scoped.md").write_text('---\npaths:\n  - "**/*.py"\n---\n# scoped\n' + "x" * 5000)

    if kind == "healthy":
        (mem / "MEMORY.md").write_text("# Memory Index\n\n- [A](a.md) — 短いフック\n")
        (mem / "a.md").write_text("---\nname: a\n---\n本文 [[a]]\n")
    elif kind == "bloated_index":
        long_hook = "- [A](a.md) — " + "とても長いフックの説明が延々と続く" * 12
        (mem / "MEMORY.md").write_text("# Memory Index\n\n" + long_hook + "\n")
        (mem / "a.md").write_text("---\nname: a\n---\n本文\n")
    elif kind == "broken_links":
        (mem / "MEMORY.md").write_text(
            "# Memory Index\n\n- [A](a.md) — フック\n- [Ghost](ghost.md) — 本体が無い\n")
        (mem / "a.md").write_text("---\nname: a\n---\n本文 [[no-such-memory]]\n")
        (mem / "orphan.md").write_text("---\nname: orphan\n---\n索引に載っていない\n")
    elif kind == "oversize":
        (home / ".claude" / "CLAUDE.md").write_text("x" * 200_000)
        (mem / "MEMORY.md").write_text("# Memory Index\n\n- [A](a.md) — 短い\n")
        (mem / "a.md").write_text("---\nname: a\n---\n本文\n")
    return home, project


def run_case(case: dict) -> tuple:
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as td:
        # measure.py は project を resolve() してから memory dir を導出する。
        # macOS では /tmp が /private/tmp への symlink なので、フィクスチャ側も
        # resolve 済みパスで作らないと encode 名がズレて「索引なし」になる
        # （初回実装で実際に踏んだ: healthy が索引なしのまま偶然 PASS していた）。
        home, project = build_fixture(Path(td).resolve(), case["fixture"])
        r = subprocess.run(
            [sys.executable, str(MEASURE), "--project", str(project), "--home", str(home)],
            capture_output=True, text=True,
        )
        try:
            out = json.loads(r.stdout)
        except json.JSONDecodeError:
            return False, f"JSON parse 失敗: {r.stdout[:120]!r} / stderr {r.stderr[:120]!r}"
        errs = []
        if out.get("verdict") != case["expect_verdict"]:
            errs.append(f"verdict {out.get('verdict')!r} != {case['expect_verdict']!r}")
        if r.returncode != case["expect_exit"]:
            errs.append(f"exit {r.returncode} != {case['expect_exit']}")
        for frag in case.get("expect_breach_contains", []):
            if not any(frag in b for b in out.get("breaches", [])):
                errs.append(f"breach に {frag!r} が無い: {out.get('breaches')}")
        if case.get("expect_no_breach") and out.get("breaches"):
            errs.append(f"breach が空でない: {out['breaches']}")
        if case.get("expect_index_exists") and not out.get("index", {}).get("exists"):
            errs.append("索引が見つかっていない（フィクスチャ配線ミスの検知）")
        if "expect_unresolved_wiki" in case:
            got = len(out.get("index", {}).get("unresolved_wiki_links", []))
            if got != case["expect_unresolved_wiki"]:
                errs.append(f"unresolved_wiki_links {got} != {case['expect_unresolved_wiki']}")
        return (not errs), "; ".join(errs)


def main() -> int:
    cases = json.loads((HERE / "evals.json").read_text())
    passed = 0
    for c in cases:
        runner = run_inventory_case if c.get("tool") == "inventory" else run_case
        ok, detail = runner(c)
        print(f"{'PASS' if ok else 'FAIL'}  {c['name']}" + (f"  ({detail})" if detail else ""))
        passed += ok
    print(f"\npass_rate: {passed}/{len(cases)}")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
