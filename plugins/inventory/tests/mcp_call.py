#!/usr/bin/env python3
"""Talk to the inventory MCP server over stdio the way Claude Code does, and print the results.

    mcp_call.py [--value] SQL ...        one execute_sql call per SQL argument
    mcp_call.py --file FILE              one execute_sql call per statement in FILE (statements end with ';' at line end)
    mcp_call.py --tool NAME              call another tool (for example apply_migrations) with no arguments
    mcp_call.py --list                   print the tool names from tools/list

Each call prints one line: the tool's JSON result, or "ERROR: <message>" for a tool error.
With --value, a result with rows prints only the first column of the first row ("" if there are no rows,
NULL for a SQL NULL), so a test can compare it as a plain word.

The server runs as `python3 server/inventory_mcp.py` unless INVENTORY_SERVER_CMD overrides it
(the Postgres runner uses `uv run --script`, which brings psycopg). The environment is passed through.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "server" / "inventory_mcp.py"


def main():
    args = sys.argv[1:]
    value = "--value" in args
    args = [a for a in args if a != "--value"]
    if args[:1] == ["--file"]:
        text = Path(args[1]).read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("--")]
        calls = [("execute_sql", {"query": s.strip()}) for s in "\n".join(lines).split(";\n") if s.strip()]
    elif args[:1] == ["--tool"]:
        calls = [(args[1], {})]
    elif args[:1] == ["--list"]:
        calls = []
    else:
        calls = [("execute_sql", {"query": s}) for s in args]

    cmd = shlex.split(os.environ.get("INVENTORY_SERVER_CMD", "")) or [sys.executable]
    msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "inventory-tests", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]
    for i, (name, arguments) in enumerate(calls, start=2):
        msgs.append({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                     "params": {"name": name, "arguments": arguments}})
    stdin = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs).encode("utf-8")
    p = subprocess.run(cmd + [str(SERVER)], input=stdin, capture_output=True, timeout=120)
    replies = {}
    for line in p.stdout.decode("utf-8").splitlines():
        r = json.loads(line)
        replies[r.get("id")] = r
    if 0 not in replies:
        sys.exit(f"server did not answer initialize (exit {p.returncode}): {p.stderr.decode('utf-8', 'replace')}")
    if not calls:
        print(",".join(t["name"] for t in replies[1]["result"]["tools"]))
        return
    for i in range(2, len(calls) + 2):
        r = replies.get(i, {})
        res = r.get("result") or {}
        text = (res.get("content") or [{}])[0].get("text", json.dumps(r.get("error")))
        if res.get("isError") or "error" in r:
            print("ERROR: " + text.replace("\n", " "))
            continue
        if value:
            out = json.loads(text)
            rows = out.get("rows")
            if rows is None:
                print(out.get("rowcount"))
            elif not rows:
                print("")
            else:
                v = rows[0][0]
                print("NULL" if v is None else v)
        else:
            print(text)


if __name__ == "__main__":
    main()
