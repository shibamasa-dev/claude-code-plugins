#!/usr/bin/env python3
"""Record published Artifacts in each project's .artifacts/.

Called from PostToolUse (matcher ^Artifact$).
- publish  ... append one line to ledger.jsonl and rebuild index.html
- list     ... append the response's updatedAt as sync lines, **only for ids already in the ledger**
              (list mixes all projects, so it never creates new rows)
Whatever happens, stdout stays empty and it always exits 0. It never stops the tool.
"""
import json, os, sys, subprocess, pathlib, tempfile, html
from datetime import datetime


def project_root(cwd: str) -> str:
    """Fold a worktree into the parent repo's root (so deleting the worktree does not delete the ledger)."""
    d = os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd()
    try:
        r = subprocess.run(
            ["git", "-C", d, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return str(pathlib.Path(r.stdout.strip()).parent)
    except Exception:
        pass
    return d


def rel_src(path, root) -> str | None:
    """The src_path kept in the ledger. **Never write an absolute path as is.**

    The ledger is tracked by git, so the local user name, worktree ID and directory layout would leak
    to anyone reading the repo (this happened before: CodeRabbit flagged it in a PR review).
    Inside the project it becomes repo-relative; outside (scratchpad etc.) only the file name is kept.
    """
    if not path:
        return None
    try:
        pp = pathlib.Path(path)
        return str(pp.resolve().relative_to(pathlib.Path(root).resolve()))
    except (ValueError, OSError):
        return pathlib.Path(path).name


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def read_rows(ledger: pathlib.Path):
    if not ledger.exists():
        return []
    out = []
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def fold(rows):
    """Fold by artifact_id. Added = first publish / last updated = the later of the last publish and remote."""
    by = {}
    for r in rows:
        aid = r.get("artifact_id")
        if not aid:
            continue
        e = by.setdefault(aid, {"artifact_id": aid, "url": "", "title": "", "description": "",
                                "favicon": "", "publishes": 0, "first": None, "last": None,
                                "remote": None, "version": ""})
        ev = r.get("event")
        if ev == "publish":
            e["publishes"] += 1
            ts = parse_ts(r.get("ts"))
            if ts:
                if e["first"] is None or ts < e["first"]:
                    e["first"] = ts
                if e["last"] is None or ts > e["last"]:
                    e["last"] = ts
            for k in ("url", "title", "description", "favicon", "version"):
                if r.get(k):
                    e[k] = r[k]
        elif ev == "sync":
            ts = parse_ts(r.get("updated_at"))
            if ts and (e["remote"] is None or ts > e["remote"]):
                e["remote"] = ts
            for k in ("url", "title", "favicon"):
                if r.get(k):
                    e[k] = r[k]
    return by


def fmt(dt):
    if dt is None:
        return "—"
    try:
        return dt.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return dt.strftime("%Y-%m-%d")


def render(entries, root: str) -> str:
    def last_of(e):
        c = [x for x in (e["last"], e["remote"]) if x is not None]
        return max(c) if c else None

    items = sorted(entries.values(), key=lambda e: (last_of(e) or e["first"] or datetime.min.replace(tzinfo=None).astimezone()), reverse=True)
    rows = []
    for e in items:
        t = html.escape(e["title"] or e["artifact_id"][:8])
        d = html.escape(e["description"] or "")
        fav = html.escape(e["favicon"] or "📄")
        url = html.escape(e["url"] or "")
        n = e["publishes"]
        badge = f'<span class="n">{n}</span>' if n > 1 else ""
        rows.append(
            f'<tr><td class="ic">{fav}</td>'
            f'<td><a href="{url}">{t}</a>{badge}<div class="d">{d}</div></td>'
            f'<td class="dt">{fmt(e["first"])}</td>'
            f'<td class="dt">{fmt(last_of(e))}</td></tr>')
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    name = html.escape(pathlib.Path(root).name)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Artifacts — {name}</title>
<style>
:root{{--bg:#fbfbfa;--fg:#1a1a19;--mut:#6b6b68;--line:#e5e4e1;--card:#fff;--link:#1a5fb4}}
@media(prefers-color-scheme:dark){{:root{{--bg:#191918;--fg:#ecebe8;--mut:#9a9995;--line:#33322f;--card:#212120;--link:#8ab4f8}}}}
*{{box-sizing:border-box}}
body{{margin:0;padding:32px 20px;background:var(--bg);color:var(--fg);
 font:15px/1.6 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif}}
.wrap{{max-width:920px;margin:0 auto}}
h1{{font-size:20px;margin:0 0 4px}}
.sub{{color:var(--mut);font-size:13px;margin-bottom:24px}}
table{{width:100%;border-collapse:collapse;background:var(--card);
 border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th{{text-align:left;font-size:12px;font-weight:600;color:var(--mut);
 padding:10px 12px;border-bottom:1px solid var(--line)}}
td{{padding:12px;border-bottom:1px solid var(--line);vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.ic{{width:34px;font-size:18px}}
.dt{{width:104px;color:var(--mut);font-size:13px;white-space:nowrap;font-variant-numeric:tabular-nums}}
a{{color:var(--link);text-decoration:none;font-weight:600}}
a:hover{{text-decoration:underline}}
.d{{color:var(--mut);font-size:13px;margin-top:3px}}
.n{{display:inline-block;margin-left:7px;padding:1px 6px;border-radius:9px;
 background:var(--line);color:var(--mut);font-size:11px;font-weight:600}}
.empty{{color:var(--mut);padding:24px;text-align:center}}
</style>
<div class="wrap">
<h1>Artifacts — {name}</h1>
<div class="sub">{len(items)} items · as of {now} · the number badge is the publish count</div>
<table>
<thead><tr><th></th><th>Title / description</th><th>Added</th><th>Last updated</th></tr></thead>
<tbody>
{chr(10).join(rows) if rows else '<tr><td colspan="4" class="empty">Nothing yet</td></tr>'}
</tbody></table>
</div>
"""


def atomic_write(path: pathlib.Path, text: str):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def main():
    d = json.load(sys.stdin)
    if d.get("tool_name") != "Artifact":
        return
    root = pathlib.Path(project_root(d.get("cwd", "")))
    ledger = root / ".artifacts" / "ledger.jsonl"
    index = ledger.parent / "index.html"
    resp = d.get("tool_response")
    new = []

    if not isinstance(resp, dict):
        pass
    elif resp.get("artifact_id") and resp.get("url"):         # publish
        ti = d.get("tool_input") or {}
        new.append({
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "event": "publish",
            "artifact_id": resp["artifact_id"],
            "url": resp["url"],
            "title": resp.get("title"),
            "description": ti.get("description"),
            "favicon": ti.get("favicon"),
            "updated": resp.get("updated"),
            "version": resp.get("version"),
            "src_path": rel_src(resp.get("path") or ti.get("file_path"), root),
            "session_id": d.get("session_id"),
        })
    elif isinstance(resp.get("artifacts"), list):             # list -> sync update dates of known ids only
        known = {r.get("artifact_id") for r in read_rows(ledger)}
        for a in resp["artifacts"] if known else []:
            url = a.get("url") or ""
            aid = url.rstrip("/").rsplit("/", 1)[-1]
            if aid in known and a.get("updatedAt"):
                new.append({
                    "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "event": "sync", "artifact_id": aid, "url": url,
                    "title": a.get("title"), "favicon": a.get("favicon"),
                    "updated_at": a["updatedAt"],
                })
    if not new:
        # even with nothing appended, rebuild the index from the ledger if it is gone
        if ledger.exists() and not index.exists():
            atomic_write(index, render(fold(read_rows(ledger)), str(root)))
        return

    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as f:            # append-only (safe with concurrent publishes)
        for r in new:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    atomic_write(index, render(fold(read_rows(ledger)), str(root)))


if __name__ == "__main__":      # importable so the index alone can be rebuilt
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
