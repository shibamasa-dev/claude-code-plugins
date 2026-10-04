#!/usr/bin/env python3
"""PreToolUse hook: Write の repo-structure ガード。

判定に使う値（許すファイル名・サブフォルダ規定セット・スクリプト拡張子・例外）を
**このスクリプトは持たない。** 仕様ファイルの `<!-- guard:… -->` ブロックを実行時に読む。
仕様ファイルは上から順に最初に見つかったものを使う:
  1. 環境変数 `FILE_GUARD_SPEC`（設定されていればこれだけを見る。無ければ何もしない）
  2. `~/.claude/rules/repo-structure.md`（ユーザーの規約）
  3. プラグイン同梱の `repo-structure.md`（既定）

なぜそうするか（2026-09-23）:
  以前は散文（rules）と実装（このファイル）に同じ規約が別表現で存在していた。そして
  **実際にズレていた** — skill レイアウトの例外は2つの実害（2026-09-17 の 166 件誤検知、
  2026-09-21 の配布スキルの誤検知）から実装にだけ入り、5週間たっても散文に書かれていなかった。
  散文を読んだ人は「scripts/ 直下は常に禁止」と理解するのに、実装は skill 配下を見逃す。
  ブロックを1行直せば、hook の挙動も deny メッセージも同時に変わる形にした。

強制点（値は SPEC 側・ここには書かない）:
  - docs/ 直下への .md 新規作成を deny（許可ファイル名は guard:docs-allow-filenames）
  - scripts/ 直下へのスクリプト新規作成を deny（拡張子は guard:script-extensions）
  - 例外は guard:exemptions の ID で有効・無効が決まる

既存ファイルの上書きは対象外（規約は「新規に置かない」。既存文書はついで移動でよい）。
matcher は Write のみ（Edit は既存ファイル対象なので登録しない）。

設計上の約束:
  - **`FILE_GUARD_SPEC` が指す SPEC が無ければ何もしない。** 明示的に外した利用者には関係が無い。
  - **SPEC があるのに読めなければ Write を止めない。** ガードの不調で作業を止めるのは過剰。
    ただし黙って通すと「規約チェック済み」と誤認させるので、通らなかったことを注入する
    （design-lint.py と同じ方針）。
"""
import json
import os
import re
import sys

def resolve_spec() -> str:
    env = os.environ.get("FILE_GUARD_SPEC")
    if env:
        return os.path.expanduser(env)
    user = os.path.expanduser("~/.claude/rules/repo-structure.md")
    if os.path.exists(user):
        return user
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "repo-structure.md")


SPEC = resolve_spec()


def read_block(spec_text: str, tag: str) -> list:
    """SPEC 内の <!-- guard:TAG --> ... <!-- /guard:TAG --> から "- " 行を取り出す。"""
    m = re.search(
        rf"<!--\s*guard:{re.escape(tag)}\s*-->(.*?)<!--\s*/guard:{re.escape(tag)}\s*-->",
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


def split_kv(entries: list) -> list:
    """`key: 説明` 行を (key, 説明) に割る。`:` が無ければ説明は空。"""
    out = []
    for e in entries:
        k, sep, v = e.partition(":")
        out.append((k.strip(), v.strip() if sep else ""))
    return out


def allow_with_notice(text: str) -> None:
    """Write は止めずに、検証できなかったことだけ伝える。"""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": text,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Write":
        sys.exit(0)
    fp = (data.get("tool_input") or {}).get("file_path", "")
    if not fp or os.path.exists(fp):
        sys.exit(0)  # 既存ファイルの上書きは規約対象外

    norm = os.path.normpath(fp)
    parts = norm.split(os.sep)
    parent = os.path.basename(os.path.dirname(norm))
    name = os.path.basename(norm)
    ext = os.path.splitext(name)[1].lower()

    # docs/ でも scripts/ でもないなら、SPEC を読むまでもない（毎 Write で走るので早く抜ける）
    if parent not in ("docs", "scripts"):
        sys.exit(0)

    try:
        spec_text = open(SPEC, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        sys.exit(0)  # FILE_GUARD_SPEC で存在しないパスを指した＝明示的に外している
    except OSError as e:
        allow_with_notice(
            f"【repo-structure ガード 未実行】{fp}\n"
            f"規約を読めなかった（{type(e).__name__}）: {SPEC}\n"
            f"配置ルールを検証していない。**規約チェック済みとして扱わないこと。**"
        )

    allow_names = read_block(spec_text, "docs-allow-filenames")
    subfolders = split_kv(read_block(spec_text, "docs-subfolders"))
    script_ext = {e.lower() for e in read_block(spec_text, "script-extensions")}
    exemptions = {k for k, _ in split_kv(read_block(spec_text, "exemptions"))}

    if not (allow_names and subfolders and script_ext):
        allow_with_notice(
            f"【repo-structure ガード 未実行】{fp}\n"
            f"{SPEC} から guard ブロックを取り出せなかった（マーカーの破損か形式変更）。\n"
            f"配置ルールを検証していない。**規約チェック済みとして扱わないこと。**"
        )

    # ---- 例外（有効・無効は SPEC の ID で決まる）
    # skill は `<skill>/scripts/` 直下にスクリプトを置くのが正しい形なので対象外にする。
    if "path-component-skills" in exemptions and "skills" in parts:
        sys.exit(0)
    if "sibling-skill-md" in exemptions:
        parent_dir = os.path.dirname(norm)
        if os.path.basename(parent_dir) == "scripts" and os.path.exists(
                os.path.join(os.path.dirname(parent_dir), "SKILL.md")):
            sys.exit(0)

    reason = None
    if parent == "docs" and ext == ".md" and name not in allow_names:
        nav = " / ".join(f"{q}→{k}" for k, q in subfolders if q)
        reason = (
            f"🛑 repo-structure-guard: docs/ 直下に .md を置かない"
            f"({'・'.join(allow_names)} のみ例外)。"
            f"{' '.join(k + '/' for k, _ in subfolders)} のサブフォルダへ"
            f"({nav})。"
        )
    elif parent == "scripts" and ext in script_ext:
        reason = (
            "🛑 repo-structure-guard: scripts/ 直下にスクリプトを置かない。"
            "機能・ドメイン単位のサブフォルダへ(例: scripts/scheduler/)。"
        )

    if reason:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason + f"\n(規約の正典: {SPEC})",
            }
        }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
