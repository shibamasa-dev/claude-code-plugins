#!/usr/bin/env python3
"""スキルに作った環境の固有情報が混ざっていないかを決定論で調べる（skill-lint の前処理層）。

  python3 lint.py <スキルのディレクトリ> [--denylist PATH] [--json]

denylist（具体的な名前・ホスト）は配布物に入れず、build_denylist.py が生成した
${XDG_CONFIG_HOME:-~/.config}/skill-lint/denylist.json から読む。ここに書くのは汎用の正規表現だけ。
evals/fixtures/ 配下は意図的に漏れを含むテスト用データなので既定で除外する。
行内に `skill-lint: ignore` がある行は調べない。
exit 0 = error なし（warn のみ含む）/ 1 = error あり / 2 = 引数エラー。
"""
import argparse, fnmatch, json, os, re, shutil, subprocess, sys, tempfile

DEFAULT_DENYLIST = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "skill-lint", "denylist.json")
IGNORE_MARK = "skill-lint: ignore"
SKIP_DIRS = {".git", "node_modules", "__pycache__"}
SKIP_FILES = {".DS_Store"}
FIXTURE_DIR = "evals/fixtures/"  # 意図的に漏れを含むテストデータ。どの深さにあっても除外する
MANIFESTS = (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
RE_PUBLISHER = re.compile(r'^\s*"(?:name|author|owner|homepage|repository|url)"\s*:')  # manifest の公開者情報

SEVERITY = {"identity": "error", "path": "error", "network": "error", "structure": "error",
            "tracker": "warn", "provenance": "warn"}
FIX = {
    "identity": "人名・組織名・アカウント名は役割（「ユーザー」「起動元」等）に置き換えるか、経緯の括弧ごと消す",
    "path": "個人のディレクトリを既定値にしない。引数・環境変数で受け、例は `<project-root>` のようなプレースホルダにする",
    "network": "ホスト名は環境変数か設定ファイルから読む。文中の例はプレースホルダにする",
    "tracker": "私的な issue/PR 番号は消し、必要なら理由を本文で書く。公開 upstream の参照なら行に `skill-lint: ignore` を付ける",
    "provenance": "日付と誰が決めたかは消し、ルールとその理由だけ残す（経緯は git log / issue に置く）",
    "structure": "実行時データはスキルの外（例: `~/.local/state/<skill>/`）へ移し、スキル配下から消す",
}

# 汎用パターン（具体名は入れない）
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
RE_EMAIL_OK = re.compile(r"@(?:example\.(?:com|org|net)|users\.noreply\.github\.com)$")
RE_HOME_ABS = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([A-Za-z0-9._-]+)[/\\]")  # skill-lint: ignore
HOME_ABS_OK = {"Shared", "runner", "user", "username", "USER", "USERNAME", "you", "me", "name"}
RE_TILDE_PATH = re.compile(r"(?:~|\$HOME|\$\{HOME\})/[^\s`'\")\]>,;{}]+")
TILDE_OK_PREFIXES = ("/.claude/", "/.config/", "/.local/", "/.cache/")
RE_TAILNET = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.ts\.net\b")  # skill-lint: ignore
RE_TRACKER = re.compile(r"(?<![&\w#])(?:[\w.-]+/)?(?:[A-Za-z][\w.-]*)?#\d+(?![\w])")
RE_DATE = re.compile(r"(?<!\d)(?:20\d{2}-\d{1,2}-\d{1,2}|20\d{2}/\d{1,2}/\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)(?!\d)")
RE_DECISION = re.compile(r"確定|承認|指示|判断|確認")
RE_FM_SKIP = re.compile(r"^\s*(?:last_reviewed|review_after)\s*:")
STRUCT_DIRS = {"logs", ".trash"}
STRUCT_GLOBS = ("*.db", "*.db-wal", "*.db-shm", "*.sqlite", "*.sqlite3", "*.jsonl", "*.log")


def load_denylist(path):
    """{"names": [...], "hosts": [...]} を auto と manual から合わせて返す。無ければ None。"""
    if not path or not os.path.exists(path):
        return None
    data = json.load(open(path, encoding="utf-8"))
    out = {"names": set(), "hosts": set()}
    for sec in ("auto", "manual"):
        for key in ("names", "hosts"):
            for t in (data.get(sec) or {}).get(key) or []:
                if isinstance(t, str) and t.strip():
                    out[key].add(t.strip())
    return {k: sorted(v, key=len, reverse=True) for k, v in out.items()}


def iter_files(root):
    """(相対パス, 絶対パス, 除外か) を返す。"""
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for f in sorted(files):
            if f in SKIP_FILES:
                continue
            ab = os.path.join(d, f)
            rel = os.path.relpath(ab, root).replace(os.sep, "/")
            yield rel, ab, rel.startswith(FIXTURE_DIR) or ("/" + FIXTURE_DIR) in rel


def structure_findings(rel):
    parts = rel.split("/")
    out = []
    for p in parts[:-1]:
        if p in STRUCT_DIRS:
            out.append(("%s/ 配下の実行時データ" % p, p + "/"))
            break
    if any(fnmatch.fnmatch(parts[-1], g) for g in STRUCT_GLOBS):
        out.append(("実行時データらしい拡張子", parts[-1]))
    return out


def read_text(ab):
    try:
        b = open(ab, "rb").read()
    except OSError:
        return None
    if b"\0" in b[:8192]:
        return None
    return b.decode("utf-8", errors="replace")


def scan_line(line, deny):
    """1 行から (category, match, message) を返す。"""
    hits = []
    if deny:
        for t in deny["names"]:
            if t in line:
                hits.append(("identity", t, "denylist の名前に一致"))
        for t in deny["hosts"]:
            if t in line:
                hits.append(("network", t, "denylist のホスト名に一致"))
    for m in RE_EMAIL.finditer(line):
        if not RE_EMAIL_OK.search(m.group(0)):
            hits.append(("identity", m.group(0), "メールアドレス"))
    for m in RE_HOME_ABS.finditer(line):
        if m.group(1) not in HOME_ABS_OK:
            hits.append(("path", m.group(0), "ユーザーのホーム配下の絶対パス"))
    for m in RE_TILDE_PATH.finditer(line):
        s = m.group(0)
        rest = s[s.index("/"):]
        if rest.startswith(TILDE_OK_PREFIXES):
            continue
        if deny and any(t in s for t in deny["names"] + deny["hosts"]):
            hits.append(("path", s, "denylist の名前を含むホーム配下のパス"))
    for m in RE_TAILNET.finditer(line):
        hits.append(("network", m.group(0), "tailnet のホスト名"))
    for m in RE_TRACKER.finditer(line):
        hits.append(("tracker", m.group(0), "issue/PR 番号の参照"))
    d = RE_DATE.search(line)
    k = RE_DECISION.search(line)
    if d and k:
        hits.append(("provenance", "%s … %s" % (d.group(0), k.group(0)), "日付つきの決定の経緯"))
    return hits


def run_gitleaks(root):
    exe = shutil.which("gitleaks")
    if not exe:
        return {"status": "未実施", "reason": "gitleaks が PATH に無い"}
    fd, rep = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        for args in (["dir", root], ["detect", "--no-git", "--source", root]):
            r = subprocess.run([exe] + args + ["--no-banner", "--report-format", "json", "--report-path", rep, "--exit-code", "0"],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if r.returncode == 0:
                try:
                    leaks = json.load(open(rep)) or []
                except ValueError:
                    leaks = []
                return {"status": "実施", "leaks": [
                    {"file": os.path.relpath(x.get("File", ""), root), "line": x.get("StartLine"), "rule": x.get("RuleID")}
                    for x in leaks]}
        return {"status": "失敗", "reason": (r.stderr or r.stdout).strip()[:300]}
    finally:
        os.unlink(rep)


def lint(root, denylist_path, use_gitleaks=True):
    root = os.path.abspath(os.path.expanduser(root))
    deny = load_denylist(denylist_path)
    findings, excluded, scanned = [], [], 0
    for rel, ab, is_excluded in iter_files(root):
        if is_excluded:
            excluded.append(rel)
            continue
        scanned += 1
        for msg, m in structure_findings(rel):
            findings.append({"file": rel, "line": 0, "category": "structure", "match": m, "message": msg, "text": ""})
        text = read_text(ab)
        if text is None:
            continue
        lines = text.splitlines()
        fm_end = 0
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    fm_end = i
                    break
        for i, line in enumerate(lines, 1):
            if IGNORE_MARK in line:
                continue
            if i - 1 <= fm_end and fm_end and RE_FM_SKIP.match(line):
                continue
            if rel.endswith(MANIFESTS) and RE_PUBLISHER.match(line):
                continue
            for cat, m, msg in scan_line(line, deny):
                findings.append({"file": rel, "line": i, "category": cat, "match": m, "message": msg, "text": line.strip()[:200]})
    for f in findings:
        f["severity"] = SEVERITY[f["category"]]
        f["fix"] = FIX[f["category"]]
    return {
        "root": root,
        "denylist": {"path": denylist_path, "loaded": deny is not None,
                     "names": len(deny["names"]) if deny else 0, "hosts": len(deny["hosts"]) if deny else 0},
        "scanned_files": scanned,
        "excluded_files": excluded,
        "gitleaks": run_gitleaks(root) if use_gitleaks else {"status": "未実施", "reason": "--no-gitleaks"},
        "summary": {"error": sum(f["severity"] == "error" for f in findings),
                    "warn": sum(f["severity"] == "warn" for f in findings)},
        "findings": findings,
    }


def print_human(res):
    d = res["denylist"]
    print("対象: %s（%d ファイル、除外 %d: evals/fixtures/）" % (res["root"], res["scanned_files"], len(res["excluded_files"])))
    print("denylist: %s" % ("%s（名前 %d・ホスト %d）" % (d["path"], d["names"], d["hosts"]) if d["loaded"]
                             else "未読込（%s が無い。build_denylist.py で作る）" % d["path"]))
    g = res["gitleaks"]
    print("gitleaks: %s" % (g["status"] + ("（%s）" % g["reason"] if g.get("reason") else "（%d 件）" % len(g.get("leaks", [])))))
    for x in g.get("leaks", []):
        print("  secret: %s:%s %s" % (x["file"], x["line"], x["rule"]))
    order = ["identity", "path", "network", "structure", "tracker", "provenance"]
    for cat in order:
        fs = [f for f in res["findings"] if f["category"] == cat]
        if not fs:
            continue
        print("\n[%s] %s %d 件 — 直し方: %s" % (SEVERITY[cat], cat, len(fs), FIX[cat]))
        for f in fs:
            loc = "%s:%d" % (f["file"], f["line"]) if f["line"] else f["file"]
            print("  %s  %s「%s」" % (loc, f["message"], f["match"]))
    s = res["summary"]
    print("\n合計: error %d / warn %d" % (s["error"], s["warn"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("skill_dir")
    ap.add_argument("--denylist", default=DEFAULT_DENYLIST)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-gitleaks", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(os.path.expanduser(a.skill_dir)):
        print("ディレクトリが無い: %s" % a.skill_dir, file=sys.stderr)
        sys.exit(2)
    res = lint(a.skill_dir, os.path.expanduser(a.denylist), not a.no_gitleaks)
    if a.json:
        json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print_human(res)
    sys.exit(1 if res["summary"]["error"] else 0)


if __name__ == "__main__":
    main()
