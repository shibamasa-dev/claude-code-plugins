#!/usr/bin/env python3
"""PostToolUse hook: lint DESIGN.md after it is edited and inject any findings so Claude fixes them.

The matcher is "Edit|Write" (**it can only match tool names**, so it cannot filter by path).
Files other than DESIGN.md are rejected by basename and exit immediately: no output, fully silent.
So python3 starts once per edit, but non-target files return within tens of ms.

Why here and not pre-commit (decided 2026-09-10):
  Fixing it in the same session right after the edit is faster than a commit gate.
  pre-commit has the advantage of also catching the user's manual edits, but we do not take that here.

Why @latest:
  The user explicitly asked for it ("use the latest @google/design.md"). Measured: @latest takes
  about 4.2 s and needs the network; pinning @0.4.0 takes about 2.2 s and works offline. It is an
  alpha tool, so a breaking change could make this fail. To pin, just change the version in CMD.

If lint fails to run (no network, npx failure), **do not pass silently**: inject a message saying
it could not be verified. A silent pass would be mistaken for "linted".
"""
import json
import os
import subprocess
import sys

TARGET = "DESIGN.md"
CMD = ["npx", "-y", "@google/design.md@latest", "lint"]
TIMEOUT = 45


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if not str(data.get("tool_name", "")).endswith(("Edit", "Write")):
        sys.exit(0)

    path = (data.get("tool_input") or {}).get("file_path") or ""
    if os.path.basename(path) != TARGET or not os.path.isfile(path):
        sys.exit(0)  # non-target files: fully silent

    try:
        proc = subprocess.run(
            CMD + [path], capture_output=True, text=True, timeout=TIMEOUT
        )
        report = json.loads(proc.stdout)
    except Exception as e:
        emit(
            f"[DESIGN.md lint NOT RUN] {path}\n"
            f"Could not run lint ({type(e).__name__}): no network or npx failed.\n"
            f"It is unverified, so run `npx -y @google/design.md@latest lint {path}` by hand."
        )
        return

    summary = report.get("summary") or {}
    errors, warnings = summary.get("errors", 0), summary.get("warnings", 0)
    if not errors and not warnings:
        sys.exit(0)  # stay silent when clean

    lines = [f"[DESIGN.md lint] {path} — errors {errors} / warnings {warnings}"]
    for f in report.get("findings", []):
        if f.get("severity") == "info":
            continue
        where = f.get("path") or "-"
        lines.append(f"  [{f.get('severity')}] {where}: {f.get('message')} ({f.get('rule')})")
    lines.append("**This edit broke DESIGN.md. Fix these before moving on.**")
    emit("\n".join(lines))


def emit(text: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": text,
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
