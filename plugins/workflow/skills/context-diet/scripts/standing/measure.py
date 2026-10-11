#!/usr/bin/env python3
"""context-diet mechanical layer: measure the always-loaded context and check thresholds.

Lists and measures the files loaded on every session (global/project CLAUDE.md, @import,
rules without paths, memory index) and checks whether thresholds are exceeded.
Judgment (what to cut or compress) is the LLM's job — this script only detects.

Files read only at recall time (memory bodies, reference/) are not counted as standing.
Mixing them in leads to the "many files = heavy" misdiagnosis (criteria.md rule 1).

usage: measure.py [--project DIR] [--home DIR] [--max-standing-kb 130]
                  [--max-index-avg 120] [--json]
exit 0: ok / 1: over_threshold / 2: runtime error
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

IMPORT_RE = re.compile(r"(?<![\w`(])@([\w][\w./-]*\.(?:md|ya?ml))")
INDEX_LINK_RE = re.compile(r"\]\(([\w.-]+\.md)\)")
WIKI_RE = re.compile(r"\[\[([\w-]+)\]\]")


def nbytes(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


def ascii_bytes(p: Path) -> int:
    try:
        return sum(b < 0x80 for b in p.read_bytes())
    except OSError:
        return 0


def text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def has_paths_frontmatter(body: str) -> bool:
    if not body.startswith("---"):
        return False
    end = body.find("\n---", 3)
    return end > 0 and bool(re.search(r"^paths:", body[3:end], re.M))


def resolve_imports(p: Path, seen: set) -> list:
    """Resolve one level of @import (@<file> form). Cycles and duplicates are stopped by seen."""
    out = []
    for m in IMPORT_RE.finditer(text(p)):
        t = (p.parent / m.group(1)).resolve()
        if t.exists() and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def memory_dir(project: Path, home: Path) -> Path:
    # Claude Code's projects directory naming: replace / and _ in the path with -
    enc = re.sub(r"[/_]", "-", str(project))
    return home / ".claude" / "projects" / enc / "memory"


def collect(project: Path, home: Path) -> dict:
    standing, conditional = [], []
    seen = set()

    def add(path: Path, kind: str):
        if path.exists() and path not in seen:
            seen.add(path)
            standing.append({"path": str(path), "kind": kind, "bytes": nbytes(path)})
            for imp in resolve_imports(path, seen):
                standing.append({"path": str(imp), "kind": f"{kind}:import", "bytes": nbytes(imp)})

    add(home / ".claude" / "CLAUDE.md", "global_claude_md")
    for rules_root, kind in ((home / ".claude" / "rules", "global_rule"),
                            (project / ".claude" / "rules", "project_rule")):
        if rules_root.is_dir():
            for f in sorted(rules_root.glob("*.md")):
                row = {"path": str(f), "kind": kind, "bytes": nbytes(f)}
                if has_paths_frontmatter(text(f)):
                    conditional.append(row)
                else:
                    standing.append(row)
    add(project / "CLAUDE.md", "project_claude_md")
    add(project / "AGENTS.md", "project_agents_md")
    add(project / ".claude" / "CLAUDE.md", "project_dot_claude_md")

    mem = memory_dir(project, home)
    index = mem / "MEMORY.md"
    idx = {"exists": index.exists(), "path": str(index)}
    if index.exists():
        body_files = {f.name for f in mem.glob("*.md")} - {"MEMORY.md"}
        itext = text(index)
        hooks = [ln for ln in itext.splitlines() if ln.startswith("- [")]
        linked = set(INDEX_LINK_RE.findall(itext))
        names = {re.sub(r"\.md$", "", n) for n in body_files}
        # [[link]]s that don't resolve to a memory name. A deliberate out-of-namespace
        # reference to a skill or doc name can't be told apart mechanically from a real
        # broken link to a memory that was never written, so report it as info, not a
        # breach (a human looks at it during grooming).
        unresolved_wiki = sorted({
            w for f in mem.glob("*.md") if f.name != "MEMORY.md"
            for w in WIKI_RE.findall(text(f)) if w not in names
        })
        idx.update({
            "bytes": nbytes(index),
            "entries": len(hooks),
            "body_files": len(body_files),
            "avg_line_chars": round(sum(map(len, hooks)) / len(hooks), 1) if hooks else 0,
            "max_line_chars": max(map(len, hooks), default=0),
            "missing_from_index": sorted(body_files - linked),
            "missing_bodies": sorted(linked - body_files),
            "unresolved_wiki_links": unresolved_wiki,
            "body_bytes_recall_only": sum(nbytes(f) for f in mem.glob("*.md") if f.name != "MEMORY.md"),
        })
        standing.append({"path": str(index), "kind": "memory_index", "bytes": nbytes(index)})

    return {"standing": standing, "conditional": conditional, "index": idx}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--max-standing-kb", type=float, default=130.0)
    # Default 120: Japanese hooks tend to average over 100 chars even right after tidying.
    # 100 would mean "over the limit right after a rewrite". 80 chars is ideal; 120 is the practical line.
    ap.add_argument("--max-index-avg", type=float, default=120.0)
    ap.add_argument("--json", action="store_true", help="for compatibility (output is always JSON)")
    a = ap.parse_args()

    project, home = Path(a.project).resolve(), Path(a.home).expanduser().resolve()
    if not project.is_dir():
        print(json.dumps({"error": f"project not a dir: {project}"}), file=sys.stderr)
        return 2

    data = collect(project, home)
    total = sum(r["bytes"] for r in data["standing"])
    ascii_total = sum(ascii_bytes(Path(r["path"])) for r in data["standing"])
    idx = data["index"]
    breaches = []
    if total / 1024 > a.max_standing_kb:
        breaches.append(f"standing_total {total/1024:.1f}KB > {a.max_standing_kb}KB")
    if idx.get("exists") and idx.get("avg_line_chars", 0) > a.max_index_avg:
        breaches.append(f"index_avg_line {idx['avg_line_chars']} > {a.max_index_avg}")
    for key in ("missing_from_index", "missing_bodies"):
        if idx.get(key):
            breaches.append(f"{key}: {len(idx[key])} entries")

    out = {
        "verdict": "over_threshold" if breaches else "ok",
        "breaches": breaches,
        "standing_total_bytes": total,
        "standing_total_kb": round(total / 1024, 1),
        # Rough estimate: ~4 UTF-8 bytes per token for mostly-ASCII (English) text,
        # ~3 when multi-byte text (Japanese etc.) makes up 30% or more of the bytes.
        "tokens_estimate": total // (4 if total and ascii_total / total > 0.7 else 3),
        "counts": {"standing_files": len(data["standing"]),
                   "conditional_rules": len(data["conditional"])},
        "index": idx,
        "top_standing": sorted(data["standing"], key=lambda r: -r["bytes"])[:8],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
