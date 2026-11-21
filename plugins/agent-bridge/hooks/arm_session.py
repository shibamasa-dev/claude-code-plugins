#!/usr/bin/env python3
"""PostToolUse hook on the bridge's own MCP tools: mark this session as one that talks to agents.

wait_inbox.py polls only in marked sessions, so with listen on, a message wakes a session that has been using
the bridge, not an unrelated session on the same machine. The mark is an empty file per session id, touched on
every bridge tool call; wait_inbox.py removes marks unused for 14 days.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bridge  # noqa: E402


def main():
    try:
        session = str(json.load(sys.stdin).get("session_id") or "")
    except ValueError:
        return 0
    if not session.replace("-", "").isalnum():
        return 0
    (_bridge.state_dir() / (session + ".armed")).touch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
