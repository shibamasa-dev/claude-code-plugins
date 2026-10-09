#!/usr/bin/env python3
"""スキルに作った環境の固有情報が混ざっていないかを決定論で調べる（skill-lint の前処理層）。

  python3 lint.py <スキルのディレクトリ> [--json] [--no-gitleaks]

ここに書くのは汎用の正規表現だけ。人名・社名・取引先などの固有名は正規表現では拾えないので、
reviewer（エージェント）がその場で集めた実行環境のヒントをもとに判定する。
スキル内の `.skill-lint-ignore`（1 行 1 パターン。そのファイルのあるディレクトリからの相対。末尾 `/` はディレクトリ）に
書いたパスだけ除外する。既定では何も除外しない（実データ由来のフィクスチャこそ漏れやすいため）。
行内に `skill-lint: ignore` がある行は調べない。
exit 0 = error なし（warn のみ含む）/ 1 = error あり / 2 = 引数エラー。
"""
import argparse, fnmatch, json, os, re, shutil, subprocess, sys, tempfile

IGNORE_MARK = "skill-lint: ignore"
GITLEAKS_TIMEOUT = 120
SKIP_DIRS = {".git", "node_modules", "__pycache__"}
SKIP_FILES = {".DS_Store"}
IGNORE_FILE = ".skill-lint-ignore"
MANIFESTS = (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
RE_PUBLISHER = re.compile(r'^\s*"(?:name|author|owner|homepage|repository|url)"\s*:')  # manifest の公開者情報

SEVERITY = {"identity": "error", "path": "error", "network": "error", "structure": "error", "unreadable": "error",
            "secret": "error", "tracker": "warn", "provenance": "warn"}
FIX = {
    "identity": "人名・組織名・アカウント名は役割（「ユーザー」「起動元」等）に置き換えるか、経緯の括弧ごと消す",
    "path": "個人のディレクトリを既定値にしない。引数・環境変数で受け、例は `<project-root>` のようなプレースホルダにする",
    "network": "ホスト名は環境変数か設定ファイルから読む。文中の例はプレースホルダにする",
    "tracker": "私的な issue/PR 番号は消し、必要なら理由を本文で書く。公開 upstream の参照なら行に `skill-lint: ignore` を付ける",
    "provenance": "日付と誰が決めたかは消し、ルールとその理由だけ残す（経緯は git log / issue に置く）",
    "structure": "実行時データはスキルの外（例: `~/.local/state/<skill>/`）へ移し、スキル配下から消す",
    "unreadable": "読める権限にして再実行する（読めないファイルは調べていない）",
    "secret": "secret を消し、漏れた値は失効させる。gitleaks が失敗したなら原因を直して再実行する",
}

# 汎用パターン（具体名は入れない）
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
RE_EMAIL_OK = re.compile(r"@(?:example\.(?:com|org|net)|users\.noreply\.github\.com)$")
RE_HOME_ABS = re.compile(r"(?:/Users/|/home/|[A-Za-z]:[\\/](?i:users)[\\/])([A-Za-z0-9._-]+)[/\\]")  # skill-lint: ignore
HOME_ABS_OK = {"Shared", "runner", "user", "username", "USER", "USERNAME", "you", "me", "name"}
RE_TILDE_PATH = re.compile(r"(?:~|\$HOME|\$\{HOME\})/[^\s`'\")\]>,;{}]+")
TILDE_OK_PREFIXES = ("/.claude/", "/.config/", "/.local/", "/.cache/")
# 標準パス以外のホーム起点のパスは warn。実データでは道具の置き場（ホーム直下の隠しディレクトリ・OS の標準フォルダ）が
# 個人のディレクトリ構成（自分で切った作業フォルダの階層）より多く、error にすると誤爆の方が多いため。判定は reviewer に任せる
TILDE_SEVERITY = "warn"
RE_TAILNET = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.ts\.net\b")  # skill-lint: ignore
RE_TRACKER = re.compile(r"(?<![&\w#])(?:[\w.-]+/)?(?:[A-Za-z][\w.-]*)?#\d+(?![\w])")
RE_DATE = re.compile(r"(?<!\d)(?:20\d{2}-\d{1,2}-\d{1,2}|20\d{2}/\d{1,2}/\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日)(?!\d)")
RE_DECISION = re.compile(r"確定|承認|指示|判断|確認")
RE_FM_SKIP = re.compile(r"^\s*(?:last_reviewed|review_after)\s*:")
STRUCT_DIRS = {"logs", ".trash"}
STRUCT_GLOBS = ("*.db", "*.db-wal", "*.db-shm", "*.sqlite", "*.sqlite3", "*.jsonl", "*.log")


def read_ignore(d):
    path = os.path.join(d, IGNORE_FILE)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def ignored(rel, pats):
    for p in pats:
        if p.endswith("/") and (rel + "/").startswith(p):
            return True
        if fnmatch.fnmatch(rel, p):
            return True
    return False


def iter_files(root):
    """(相対パス, 絶対パス, 除外か) を返す。除外は各階層の .skill-lint-ignore に従う。"""
    rules = []  # (ignore ファイルのあるディレクトリ, パターン)
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        pats = read_ignore(d)
        if pats:
            rules.append((d, pats))
        for f in sorted(files):
            if f in SKIP_FILES:
                continue
            ab = os.path.join(d, f)
            rel = os.path.relpath(ab, root).replace(os.sep, "/")
            ex = any(ignored(os.path.relpath(ab, base).replace(os.sep, "/"), p)
                     for base, p in rules if (ab + os.sep).startswith(base + os.sep))
            yield rel, ab, ex


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
    """テキストを返す。バイナリは None、読めなければ OSError をそのまま上げる（黙って飛ばさない）。"""
    with open(ab, "rb") as f:
        b = f.read()
    if b"\0" in b[:8192]:
        return None
    return b.decode("utf-8", errors="replace")


def scan_line(line):
    """1 行から (category, match, message, severity or None) を返す。None はカテゴリの既定の深刻度。"""
    hits = []
    for m in RE_EMAIL.finditer(line):
        if not RE_EMAIL_OK.search(m.group(0)):
            hits.append(("identity", m.group(0), "メールアドレス", None))
    for m in RE_HOME_ABS.finditer(line):
        if m.group(1) not in HOME_ABS_OK:
            hits.append(("path", m.group(0), "ユーザーのホーム配下の絶対パス", None))
    for m in RE_TILDE_PATH.finditer(line):
        s = m.group(0)
        rest = s[s.index("/"):]
        if rest.startswith(TILDE_OK_PREFIXES):
            continue
        hits.append(("path", s, "標準パス以外のホーム起点のパス（個人のディレクトリ構成でないか確かめる）", TILDE_SEVERITY))
    for m in RE_TAILNET.finditer(line):
        hits.append(("network", m.group(0), "tailnet のホスト名", None))
    for m in RE_TRACKER.finditer(line):
        hits.append(("tracker", m.group(0), "issue/PR 番号の参照", None))
    d = RE_DATE.search(line)
    k = RE_DECISION.search(line)
    if d and k:
        hits.append(("provenance", "%s … %s" % (d.group(0), k.group(0)), "日付つきの決定の経緯", None))
    return hits


def run_gitleaks(root):
    exe = shutil.which("gitleaks")
    if not exe:
        return {"status": "未実施", "reason": "gitleaks が PATH に無い"}
    fd, rep = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        for args in (["dir", root], ["detect", "--no-git", "--source", root]):
            try:
                r = subprocess.run([exe] + args + ["--no-banner", "--report-format", "json", "--report-path", rep, "--exit-code", "0"],
                                   capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=GITLEAKS_TIMEOUT)
            except subprocess.TimeoutExpired:
                return {"status": "失敗", "reason": "gitleaks が %d 秒で終わらなかった" % GITLEAKS_TIMEOUT}
            if r.returncode == 0:
                try:
                    with open(rep, encoding="utf-8") as f:
                        leaks = json.load(f) or []
                except ValueError as e:  # 読めないレポートを「検出 0 件」にしない
                    return {"status": "失敗", "reason": "gitleaks のレポートを読めない（%s）" % e}
                return {"status": "実施", "leaks": [
                    {"file": os.path.relpath(x.get("File", ""), root).replace(os.sep, "/"), "line": x.get("StartLine"), "rule": x.get("RuleID")}
                    for x in leaks]}
        return {"status": "失敗", "reason": (r.stderr or r.stdout).strip()[:300]}
    finally:
        os.unlink(rep)


def lint(root, use_gitleaks=True):
    root = os.path.abspath(os.path.expanduser(root))
    findings, excluded, scanned = [], [], 0
    for rel, ab, is_excluded in iter_files(root):
        if is_excluded:
            excluded.append(rel)
            continue
        scanned += 1
        for msg, m in structure_findings(rel):
            findings.append({"file": rel, "line": 0, "category": "structure", "match": m, "message": msg, "text": ""})
        try:
            text = read_text(ab)
        except OSError as e:
            findings.append({"file": rel, "line": 0, "category": "unreadable", "match": "", "message": "読めないので調べられていない（%s）" % e.strerror, "text": ""})
            continue
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
            publisher = rel.endswith(MANIFESTS) and RE_PUBLISHER.match(line)
            for cat, m, msg, sev in scan_line(line):
                if publisher and cat == "identity":  # 公開者の名前・連絡先は公開前提。パスやホストは調べる
                    continue
                findings.append({"file": rel, "line": i, "category": cat, "match": m, "message": msg,
                                 "text": line.strip()[:200], "severity": sev})
    gl = run_gitleaks(root) if use_gitleaks else {"status": "未実施", "reason": "--no-gitleaks"}
    for x in gl.get("leaks", []):
        if x["file"] not in excluded:
            findings.append({"file": x["file"], "line": x["line"] or 0, "category": "secret", "match": x["rule"],
                             "message": "gitleaks が secret を検出（%s）" % x["rule"], "text": ""})
    if gl["status"] == "失敗":
        findings.append({"file": "", "line": 0, "category": "secret", "match": "",
                         "message": "gitleaks が失敗したので secret を調べられていない", "text": gl.get("reason", "")})
    for f in findings:
        f["severity"] = f.get("severity") or SEVERITY[f["category"]]
        f["fix"] = FIX[f["category"]]
    return {
        "root": root,
        "scanned_files": scanned,
        "excluded_files": excluded,
        "gitleaks": gl,
        "summary": {"error": sum(f["severity"] == "error" for f in findings),
                    "warn": sum(f["severity"] == "warn" for f in findings)},
        "findings": findings,
    }


def print_human(res):
    print("対象: %s（%d ファイル、除外 %d: .skill-lint-ignore）" % (res["root"], res["scanned_files"], len(res["excluded_files"])))
    print("固有名（人名・社名・取引先）: lint では調べない。reviewer が判定する")
    g = res["gitleaks"]
    print("gitleaks: %s" % (g["status"] + ("（%s）" % g["reason"] if g.get("reason") else "（%d 件）" % len(g.get("leaks", [])))))
    for x in g.get("leaks", []):
        print("  secret: %s:%s %s" % (x["file"], x["line"], x["rule"]))
    order = ["secret", "identity", "path", "network", "structure", "tracker", "provenance"]
    for cat in order:
        fs = [f for f in res["findings"] if f["category"] == cat]
        if not fs:
            continue
        print("\n%s %d 件 — 直し方: %s" % (cat, len(fs), FIX[cat]))
        for f in fs:
            loc = "%s:%d" % (f["file"], f["line"]) if f["line"] else f["file"]
            print("  [%s] %s  %s「%s」" % (f["severity"], loc, f["message"], f["match"]))
    s = res["summary"]
    print("\n合計: error %d / warn %d" % (s["error"], s["warn"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("skill_dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-gitleaks", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(os.path.expanduser(a.skill_dir)):
        print("ディレクトリが無い: %s" % a.skill_dir, file=sys.stderr)
        sys.exit(2)
    res = lint(a.skill_dir, not a.no_gitleaks)
    if a.json:
        json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print_human(res)
    sys.exit(1 if res["summary"]["error"] else 0)


if __name__ == "__main__":
    main()
