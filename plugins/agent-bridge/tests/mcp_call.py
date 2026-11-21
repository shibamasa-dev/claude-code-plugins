#!/usr/bin/env python3
"""Talk to the agent-bridge MCP server over stdio the way Claude Code does.

    mcp_call.py --list                 print the tool names, comma-separated
    mcp_call.py TOOL [JSON_ARGS]       call one tool; print its text, or "ERROR: <text>" for a tool error

The environment (AGENT_BRIDGE_URL, AGENT_BRIDGE_TOKEN) is passed through to the server.
"""
import json
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "server" / "agent_bridge_mcp.py"


def main():
    args = sys.argv[1:]
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    if args[:1] == ["--list"]:
        msgs.append({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    else:
        arguments = json.loads(args[1]) if len(args) > 1 else {}
        msgs.append({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": args[0], "arguments": arguments}})
    stdin = "".join(json.dumps(m) + "\n" for m in msgs)
    out = subprocess.run([sys.executable, str(SERVER)], input=stdin, capture_output=True, text=True, timeout=60).stdout
    replies = {r.get("id"): r for r in map(json.loads, out.splitlines())}
    r = replies[2]
    if "error" in r:
        print("ERROR: " + r["error"]["message"])
    elif args[:1] == ["--list"]:
        print(",".join(t["name"] for t in r["result"]["tools"]))
    else:
        text = r["result"]["content"][0]["text"]
        print(("ERROR: " + text) if r["result"].get("isError") else text)


if __name__ == "__main__":
    main()
