#!/usr/bin/env python3
"""claude plugin validate が見ない2点を検査する（CI と手元で同じものを回す）。

1. skills/<dir>/SKILL.md の frontmatter の name がディレクトリ名と一致する
   （validate は name の欠落は警告しても、ディレクトリ名との食い違いは通す）
2. 公開リポに個人の環境が漏れていない: ホームディレクトリの絶対パス・メールアドレス
   （noreply と example ドメインは除く）。追加の禁止語は環境変数 BLOCKED_PATTERNS
   （改行区切りの正規表現。CI ではリポの secret から渡す）で足す。禁止語そのものを
   このファイルに書くと、それ自体が公開リポへの漏れになるため
"""
import os
import re
import subprocess
import sys

ROOT = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                      capture_output=True, text=True, check=True).stdout.strip()
FILES = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                       capture_output=True, text=True, check=True).stdout.split("\0")

INDEX = "--index" in sys.argv  # 作業ツリーでなくステージ済みの内容を読む（pre-commit 用）
LEAKS = [
    # /ro[o]t/ の [o] は、この行自体が検出に当たらないようにするため
    (re.compile(r"/Users/[A-Za-z]|/home/[a-z]|/ro[o]t/"), "ホームディレクトリの絶対パス"),
    (re.compile(r"[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|noreply\.|anthropic\.com|github\.com\b|example\.)"
                r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "メールアドレス"),
]
LEAKS += [(re.compile(p), "BLOCKED_PATTERNS")
          for p in os.environ.get("BLOCKED_PATTERNS", "").splitlines() if p.strip()]

errors = []
for f in filter(None, FILES):
    path = os.path.join(ROOT, f)
    try:
        # 読めない文字があっても飛ばさない（UTF-8 以外のファイルに紛れ込ませて素通りさせない）
        if INDEX:
            # pre-commit: コミットされるのはインデックスの中身。作業ツリーを読むと、ステージ後に
            # 作業ツリーだけ直した混入物を見逃す
            text = subprocess.run(["git", "show", f":{f}"], cwd=ROOT, capture_output=True,
                                  check=True).stdout.decode("utf-8", errors="replace")
        else:
            text = open(path, encoding="utf-8", errors="replace").read()
    except (IsADirectoryError, FileNotFoundError, subprocess.CalledProcessError):
        continue
    if f.endswith("/SKILL.md") and "/skills/" in f:
        head = text.split("---")
        m = re.search(r"^name:\s*(\S+)", head[1] if len(head) > 2 else "", re.M)
        want = os.path.basename(os.path.dirname(f))
        if not m or m.group(1).strip("\"'") != want:
            errors.append(f"{f}: frontmatter の name がディレクトリ名 '{want}' と一致しない")
    for n, line in enumerate(text.splitlines(), 1):
        for rx, what in LEAKS:
            if rx.search(line):
                errors.append(f"{f}:{n}: {what}")  # 一致した文字列は出さない（ログも公開される）
# BLOCKED_PATTERNS の一致は場所も件数も出さない。公開ログに「どの行が当たったか」が出ると、
# 外部の PR が候補語を試して社内の固有名を当てる手がかりになる（場所は手元の pre-commit で見る）
blocked = [e for e in errors if e.endswith(": BLOCKED_PATTERNS")]
if blocked and os.environ.get("HIDE_BLOCKED_LOCATIONS"):
    errors = [e for e in errors if e not in blocked] + ["社内の固有名（BLOCKED_PATTERNS）に一致する行がある"]

print("\n".join(errors) if errors else "OK")
sys.exit(1 if errors else 0)
