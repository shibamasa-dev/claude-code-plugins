#!/usr/bin/env python3
"""context-diet 機械層: 常時ロードコンテキストの実測と閾値判定。

毎セッション読み込まれるファイル（グローバル/プロジェクト CLAUDE.md・@import・
paths 無し rules・メモリ索引）を列挙して実測し、閾値超過を判定する。
判断（何を削る・圧縮する）は LLM 側の仕事 — このスクリプトは検知だけ。

recall 時のみ読まれるもの（メモリ本体・reference/）は standing に数えない。
ここを混ぜると「ファイルが多い＝重い」の誤診になる（criteria.md 基準1）。

usage: measure.py [--project DIR] [--home DIR] [--max-standing-kb 130]
                  [--max-index-avg 100] [--json]
exit 0: ok / 1: over_threshold / 2: 実行エラー
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
    """1階層の @import 解決（@<file> 形式）。循環・重複は seen で止める。"""
    out = []
    for m in IMPORT_RE.finditer(text(p)):
        t = (p.parent / m.group(1)).resolve()
        if t.exists() and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def memory_dir(project: Path, home: Path) -> Path:
    # Claude Code の projects ディレクトリ命名: パスの / と _ を - に置換
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
        # メモリ名に解決しない [[link]]。skill 名・ドキュメント名への意図的な
        # 名前空間外参照と、書かれなかったメモリへの本物のリンク切れは機械では
        # 区別できないため、breach にせず情報として出す（grooming 時に人が見る）。
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
    # 既定120: 日本語のフックは整えた直後でも平均 100 字を超えやすい。
    # 100 だと「書き直した直後に超過」の矛盾になる。80字は理想・120字が実務線。
    ap.add_argument("--max-index-avg", type=float, default=120.0)
    ap.add_argument("--json", action="store_true", help="互換用（出力は常に JSON）")
    a = ap.parse_args()

    project, home = Path(a.project).resolve(), Path(a.home).expanduser().resolve()
    if not project.is_dir():
        print(json.dumps({"error": f"project not a dir: {project}"}), file=sys.stderr)
        return 2

    data = collect(project, home)
    total = sum(r["bytes"] for r in data["standing"])
    idx = data["index"]
    breaches = []
    if total / 1024 > a.max_standing_kb:
        breaches.append(f"standing_total {total/1024:.1f}KB > {a.max_standing_kb}KB")
    if idx.get("exists") and idx.get("avg_line_chars", 0) > a.max_index_avg:
        breaches.append(f"index_avg_line {idx['avg_line_chars']} > {a.max_index_avg}")
    for key in ("missing_from_index", "missing_bodies"):
        if idx.get(key):
            breaches.append(f"{key}: {len(idx[key])}件")

    out = {
        "verdict": "over_threshold" if breaches else "ok",
        "breaches": breaches,
        "standing_total_bytes": total,
        "standing_total_kb": round(total / 1024, 1),
        "tokens_estimate": total // 3,  # 日本語主体の概算。英語主体なら /4
        "counts": {"standing_files": len(data["standing"]),
                   "conditional_rules": len(data["conditional"])},
        "index": idx,
        "top_standing": sorted(data["standing"], key=lambda r: -r["bytes"])[:8],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
