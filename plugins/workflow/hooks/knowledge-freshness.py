#!/usr/bin/env python3
"""SessionStart hook: ナレッジの鮮度切れを1行で知らせる。

なぜ必要か（実害の記録・2026-09-21）:
  ユーザーのリファレンス文書の冒頭には、手書きでこう貼られていた —
  「⚠️ 本文中の『畳むのは手動』は 2026-09-21 に撤回」。**人間が気づいて手で貼った訂正**
  であって、構造では拾えていなかった。別のナレッジベースでは INDEX.md に last_reviewed /
  review_after を持ってスキルが鮮度を見ているのに、`~/.claude` 側には同じしくみが
  無かった。古くなったことに人間が気づくしくみをナレッジ自身に組み込み、鮮度管理を
  運用者の善意ではなく構造で担保する。

**強度は WARN のみ。BLOCK しない**（重大なものは止め、育てる途中のものは気づかせる）。ナレッジが古いことでセッションを
  止めるのは過剰で、止められた側は消すか期限を延ばすかしかできない。

設計上の約束:
  - **期限切れが1件も無ければ完全に silent**（exit 0・出力ゼロ）。毎セッション走るため
  - **何が起きてもセッション開始をブロックしない**。frontmatter の YAML が壊れていても、
    ファイルが消えていても、例外を握って exit 0
  - **last_reviewed が無いファイルも「鮮度未設定」として挙げる**。設定漏れは、期限切れより
    見つけにくい（永久に警告が出ないため）
  - 初期値は最終編集日からの機械的なブートストラップであって「読み直して確認した日」では
    ないので、WARN 文でそのことを明示する（そうしないと「確認済み」と誤解される）
"""
import datetime
import json
import os
import re
import sys

ROOT = os.path.expanduser("~/.claude")
TARGETS = [
    ("rules", os.path.join(ROOT, "rules"), "*.md"),
    ("reference", os.path.join(ROOT, "reference"), "*.md"),
    ("skills", os.path.join(ROOT, "skills"), "*/SKILL.md"),
]
FM_RE = re.compile(r"\A---\n(.*?\n)---\n", re.S)
DATE_RE = re.compile(r"^review_after:\s*(20\d\d-\d\d-\d\d)\s*$", re.M)
HAS_REVIEWED = re.compile(r"^last_reviewed:\s*20\d\d-\d\d-\d\d\s*$", re.M)
MAX_LIST = 12


def iter_files():
    import glob
    for label, base, pat in TARGETS:
        for p in sorted(glob.glob(os.path.join(base, pat))):
            yield label, p


def main() -> None:
    today = datetime.date.today()
    expired, unset = [], []

    for label, path in iter_files():
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                head = f.read(4096)
        except OSError:
            continue
        m = FM_RE.match(head)
        fm = m.group(1) if m else ""
        rel = os.path.relpath(path, ROOT)

        if not HAS_REVIEWED.search(fm):
            unset.append(rel)
            continue
        d = DATE_RE.search(fm)
        if not d:
            unset.append(rel)
            continue
        try:
            due = datetime.date.fromisoformat(d.group(1))
        except ValueError:
            unset.append(rel)
            continue
        if today > due:
            expired.append((rel, (today - due).days))

    if not expired and not unset:
        sys.exit(0)  # 期限切れゼロなら完全に silent

    lines = ["【ナレッジ鮮度】"]
    if expired:
        expired.sort(key=lambda x: -x[1])
        lines.append(f"review_after を過ぎたファイルが {len(expired)} 件:")
        lines += [f"  - {rel}（{days} 日超過）" for rel, days in expired[:MAX_LIST]]
        if len(expired) > MAX_LIST:
            lines.append(f"  - （他 {len(expired) - MAX_LIST} 件）")
    if unset:
        lines.append(f"鮮度が未設定のファイルが {len(unset)} 件:")
        lines += [f"  - {rel}" for rel in unset[:MAX_LIST]]
        if len(unset) > MAX_LIST:
            lines.append(f"  - （他 {len(unset) - MAX_LIST} 件）")
    lines += [
        "",
        "これは警告であって作業を止めるものではない。**今すぐ直す必要は無い。**",
        "ただしこれらのファイルを今回のセッションで参照するなら、書いてある内容が"
        "現状と合っているかを疑って読むこと。",
        "読み直して内容が正しいと確認できたら `last_reviewed` を今日の日付へ、"
        "`review_after` をその先へ更新する。",
        "（`last_reviewed` の初期値は最終編集日から機械的に入れたブートストラップであって、"
        "誰かが読み直して確認した日ではない）",
    ]

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines),
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # 何が起きてもセッション開始を止めない
