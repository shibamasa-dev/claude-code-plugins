#!/usr/bin/env python3
"""SessionStart hook: warn once when bridge_url is set but the token did not arrive.

The token is a sensitive option kept in secure storage. When that storage cannot be read as the session starts,
the hooks and the MCP server get an empty token while bridge_url arrives as saved. Nothing needs reconfiguring, so
the warning points at /reload-plugins first. It prints one JSON line whose systemMessage is shown to the user
(a synchronous hook: an asyncRewake hook's output is not shown to the user), and never the token or its length.
Same condition as the MCP server's token_missing error. No network call; always exits 0.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bridge  # noqa: E402

WARNING = (
    "agent-bridge: bridge_url is set but the token did not reach this session (secure storage may have been "
    "unreadable at start). Run /reload-plugins or restart Claude Code; re-enter the token in the plugin's "
    "settings only if that does not help."
)


def main():
    if _bridge.option("bridge_url") and not _bridge.option("token"):
        print(json.dumps({"systemMessage": WARNING}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
