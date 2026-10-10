#!/usr/bin/env python3
"""remote-setup scaffold generator.

Usage: scaffold.py <repo-root>

生成・更新:
- scripts/remote-setup/setup.sh : 共通ランナー(常に最新テンプレで上書き)
- scripts/remote-setup/steps.sh : リポ固有 steps(無ければテンプレ配置、あれば保持)
- .claude/settings.json         : SessionStart hook をマージ(既存設定保持・重複追加しない)
"""
import json
import shutil
import stat
import sys
from pathlib import Path

HOOK_MARKER = "remote-setup/setup.sh"
HOOK_ENTRY = {
    "matcher": "startup|resume",
    "hooks": [
        {
            "type": "command",
            "command": 'bash "$CLAUDE_PROJECT_DIR"/scripts/remote-setup/setup.sh',
            "timeout": 120,
        }
    ],
}


def merge_hook(settings_path: Path) -> bool:
    """SessionStart hook を settings.json にマージする。追記したら True。"""
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError as e:
            sys.exit(f"error: {settings_path} が JSON として壊れています: {e}")
    session_start = settings.setdefault("hooks", {}).setdefault("SessionStart", [])
    for entry in session_start:
        for h in entry.get("hooks", []):
            if HOOK_MARKER in h.get("command", ""):
                return False  # 配線済み
    session_start.append(HOOK_ENTRY)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    )
    return True


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    repo = Path(sys.argv[1]).resolve()
    if not repo.is_dir():
        sys.exit(f"error: {repo} はディレクトリではありません")
    templates = Path(__file__).resolve().parent.parent / "assets" / "templates"
    dest = repo / "scripts" / "remote-setup"
    dest.mkdir(parents=True, exist_ok=True)

    setup = dest / "setup.sh"
    shutil.copy2(templates / "setup.sh", setup)
    print(f"updated: {setup}(共通部・常に上書き)")

    repo_owned = []
    for name in ("steps.sh", "environment-setup.sh"):
        f = dest / name
        repo_owned.append(f)
        if f.exists():
            print(f"kept:    {f}(リポ固有・保持)")
        else:
            shutil.copy2(templates / name, f)
            print(f"created: {f}(リポ固有 — この後で埋める)")

    for f in (setup, *repo_owned):
        f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    settings_path = repo / ".claude" / "settings.json"
    if merge_hook(settings_path):
        print(f"wired:   {settings_path} に SessionStart hook を追加")
    else:
        print(f"kept:    {settings_path}(hook 配線済み)")

    print()
    print("次にやること:")
    print("  1. steps.sh の light_steps / verify と environment-setup.sh(重い導入)を実装する")
    print("  2. ローカル安全確認: env -u CLAUDE_CODE_REMOTE bash scripts/remote-setup/setup.sh"
          " → 無出力・exit 0")
    print("  3. claude.ai/code の環境ダイアログ > Setup script に")
    print("     environment-setup.sh の【内容を丸ごと】貼り付ける(1行参照は不可:")
    print("     Setup script 実行時点ではリポジトリが存在しない前提)")


if __name__ == "__main__":
    main()
