#!/usr/bin/env python3
"""PostToolUse hook: テストケース成果物がスタイルガイドに従っているかを機械検証する。

matcher は "Edit|Write"（**ツール名しかマッチできない**ので、パスでは絞れない）。
対象外のファイルは数 ms で exit 0・出力ゼロ＝完全に silent。

なぜ必要か:
  ナレッジを構造化しても、それだけでは「ルールを知っている」状態にすぎず、守るかどうかは
  AI 任せのまま。成果物が書き込まれるたびに機械検証して初めて「ルールを破れない」になる。

**対象を絞る理由（グローバルに置いたことによる制約）**:
  この種の Hook はプロジェクトの .claude/settings.json に置けば、そのプロジェクトのテスト成果物
  だけに当たる。プラグインに入れると**全リポの全 Write/Edit に当たる**ので、
  普通の日本語文書にあいまい語が1つ入っただけで止まり、実装コードの定数名が毎回 WARN される。
  そこで**オプトイン**にした:
    1. 拡張子 .feature / .gherkin
    2. frontmatter に `testcase: true` を持つ .md
  それ以外は即 exit 0。加えて本文に "Scenario" が無ければ何も検証しない（二重の安全弁）。
  ※ この2条件により、禁止語を**例として列挙している** style-guide.md 自身は対象外になる
    （.md かつ testcase フラグ無し）。自分自身で止まる事故を構造で防いでいる。

**禁止語を持たない理由**:
  禁止語の定義はこのスクリプトに書かず、SPEC（スタイルガイド）を実行時に読む。
  定義が2箇所にあると片方だけ直してズレる。SPEC を1行足せば次回から hook の挙動も変わる。

強度設計:
  - あいまい語   → BLOCK (exit 2)。書いた本人以外には何を確認すればいいか判断できないため
  - 内部用語     → WARN。突合先の UI 用語ガイドはプロジェクト固有＝グローバルには無い。
                   突合先が無い状態で BLOCK すると直しようがないのに止まる

設計上の約束:
  - **対象外は完全に silent**（exit 0・出力なし）。全 Edit/Write で走るため
  - **SPEC が読めなければ黙って通さない**。検証できなかったことを明示して注入する
    （silent pass は「検証済み」と誤認させる。design-lint.py と同じ方針）。ただし BLOCK はしない
  - 何が起きても Write 自体は壊さない
"""
import json
import os
import re
import sys

# 同梱の testcase-generator スキルのスタイルガイド（hooks/ の隣の skills/ 配下）
SPEC = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..",
    "skills", "testcase-generator", "references", "style-guide.md",
))
TARGET_EXT = (".feature", ".gherkin")
MAX_BYTES = 512 * 1024  # 巨大ファイルは読まない（誤爆より無検証を選ぶ）


def read_block(spec_text: str, tag: str) -> list[str]:
    """SPEC 内の <!-- lint:TAG --> ... <!-- /lint:TAG --> から "- " 行を取り出す。"""
    m = re.search(
        rf"<!--\s*lint:{re.escape(tag)}\s*-->(.*?)<!--\s*/lint:{re.escape(tag)}\s*-->",
        spec_text,
        re.S,
    )
    if not m:
        return []
    return [
        line.strip()[2:].strip()
        for line in m.group(1).splitlines()
        if line.strip().startswith("- ")
    ]


def is_target(path: str) -> bool:
    if path.lower().endswith(TARGET_EXT):
        return True
    if not path.lower().endswith(".md"):
        return False
    # frontmatter の testcase: true だけを対象にする（本文のどこかに書いてあっても拾わない）
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(2048)
    except OSError:
        return False
    fm = re.match(r"^---\n(.*?)\n---", head, re.S)
    return bool(fm and re.search(r"^testcase:\s*true\s*$", fm.group(1), re.M))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not str(data.get("tool_name", "")).endswith(("Edit", "Write")):
        sys.exit(0)

    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path or not os.path.isfile(path):
        sys.exit(0)
    try:
        if os.path.getsize(path) > MAX_BYTES:
            sys.exit(0)
    except OSError:
        sys.exit(0)

    if not is_target(path):
        sys.exit(0)  # 対象外は完全に silent

    try:
        body = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        sys.exit(0)
    if "Scenario" not in body:
        sys.exit(0)  # Gherkin が入っていなければ検証するものが無い

    try:
        spec_text = open(SPEC, encoding="utf-8", errors="replace").read()
        vague = read_block(spec_text, "vague-words")
        patterns = read_block(spec_text, "internal-term-patterns")
    except OSError as e:
        warn(
            f"【テストケース検証 未実行】{path}\n"
            f"スタイルガイドを読めなかった（{type(e).__name__}）: {SPEC}\n"
            f"禁止語の定義が取れないので検証していない。**検証済みとして扱わないこと。**"
        )
    if not vague and not patterns:
        warn(
            f"【テストケース検証 未実行】{path}\n"
            f"{SPEC} から禁止語ブロックを取り出せなかった（マーカーの破損か形式変更）。\n"
            f"検証していないので、**検証済みとして扱わないこと。**"
        )

    lines = body.splitlines()
    vague_hits = [
        (i, w, ln.strip())
        for i, ln in enumerate(lines, 1)
        for w in vague
        if w in ln
    ]
    internal_hits = []
    for pat in patterns:
        try:
            rx = re.compile(pat)
        except re.error:
            continue  # SPEC 側の正規表現が壊れていても他の検証は続ける
        internal_hits += [
            (i, pat, ln.strip()) for i, ln in enumerate(lines, 1) if rx.search(ln)
        ]

    if vague_hits:
        msg = [f"🛑 テストケース検証 BLOCK: {path}", "", "**あいまい語が残っている。**"]
        msg += [f"  L{i}: 「{w}」 — {txt[:80]}" for i, w, txt in vague_hits[:15]]
        if len(vague_hits) > 15:
            msg.append(f"  （他 {len(vague_hits) - 15} 件）")
        msg += [
            "",
            "Then に書くのは「人がその場で真偽を判定できるもの」。"
            "上の語のままでは、書いた本人以外には何を確認すればいいか判断できない。",
            "具体的な表示文言・数値・ステータスに書き換えること。",
            f"（禁止語の定義: {SPEC}）",
        ]
        if internal_hits:
            msg += ["", f"※ 内部用語の疑いも {len(internal_hits)} 件ある（下の WARN 参照）。"]
            msg += [f"  L{i}: {txt[:80]}" for i, _, txt in internal_hits[:5]]
        print("\n".join(msg), file=sys.stderr)
        sys.exit(2)

    if internal_hits:
        msg = [f"⚠️ テストケース検証 WARN: {path}", "", "**内部用語が残っている可能性。**"]
        msg += [f"  L{i}: {txt[:80]}" for i, _, txt in internal_hits[:10]]
        if len(internal_hits) > 10:
            msg.append(f"  （他 {len(internal_hits) - 10} 件）")
        msg += [
            "",
            "テストケースを読むのはコードを見ていない手動テスト担当者。"
            "API パスや内部定数名のままだと、画面で何を操作すればいいかわからない。",
            "プロジェクトに UI 用語ガイド"
            "（$CLAUDE_PROJECT_DIR/.claude/knowledge/ui-terms.md）があれば突き合わせる。",
            "無い場合は推測で名前を作らず、「確認が必要な箇所」に残すこと。",
        ]
        warn("\n".join(msg))

    sys.exit(0)  # clean なら黙る


def warn(text: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
