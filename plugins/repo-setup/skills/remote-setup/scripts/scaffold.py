#!/usr/bin/env python3
"""remote-setup scaffold generator.

Usage: scaffold.py <repo-root>

Generates / updates:
- scripts/remote-setup/setup.sh : shared runner (always overwritten with the latest template)
- scripts/remote-setup/steps.sh : repo-specific steps (template placed if missing, kept if present)
- .claude/settings.json         : SessionStart hook merged in (existing settings kept, no duplicate added)
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
    """Merge the SessionStart hook into settings.json. True if it was added."""
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError as e:
            sys.exit(f"error: {settings_path} is not valid JSON: {e}")
    session_start = settings.setdefault("hooks", {}).setdefault("SessionStart", [])
    for entry in session_start:
        for h in entry.get("hooks", []):
            if HOOK_MARKER in h.get("command", ""):
                return False  # already wired
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
        sys.exit(f"error: {repo} is not a directory")
    templates = Path(__file__).resolve().parent.parent / "assets" / "templates"
    dest = repo / "scripts" / "remote-setup"
    dest.mkdir(parents=True, exist_ok=True)

    setup = dest / "setup.sh"
    shutil.copy2(templates / "setup.sh", setup)
    print(f"updated: {setup} (shared part, always overwritten)")

    repo_owned = []
    for name in ("steps.sh", "environment-setup.sh"):
        f = dest / name
        repo_owned.append(f)
        if f.exists():
            print(f"kept:    {f} (repo-specific, kept)")
        else:
            shutil.copy2(templates / name, f)
            print(f"created: {f} (repo-specific — fill it in next)")

    for f in (setup, *repo_owned):
        f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    settings_path = repo / ".claude" / "settings.json"
    if merge_hook(settings_path):
        print(f"wired:   added the SessionStart hook to {settings_path}")
    else:
        print(f"kept:    {settings_path} (hook already wired)")

    print()
    print("Next steps:")
    print("  1. Implement light_steps / verify in steps.sh and environment-setup.sh (heavy installs)")
    print("  2. Local safety check: env -u CLAUDE_CODE_REMOTE bash scripts/remote-setup/setup.sh"
          " → no output, exit 0")
    print("  3. In the claude.ai/code environment dialog > Setup script,")
    print("     paste [the whole content] of environment-setup.sh (a one-line reference does not work:")
    print("     the repository is assumed not to exist yet when the Setup script runs)")


if __name__ == "__main__":
    main()
