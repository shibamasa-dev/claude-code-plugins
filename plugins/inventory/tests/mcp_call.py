#!/usr/bin/env python3
"""Talk to the inventory MCP server over stdio the way Claude Code does, and print the results.

    mcp_call.py [--value] SQL ...        one execute_sql call per SQL argument, all to the same server process.
                                         An argument starting with ! is a shell command run between two calls
                                         (for example to cut the server's database connection); it prints nothing
    mcp_call.py --file FILE              one execute_sql call per statement in FILE (statements end with ';' at line end)
    mcp_call.py --tool NAME              call another tool (for example apply_migrations) with no arguments
    mcp_call.py --list                   print the tool names from tools/list (no tool call)

Each call prints one line: the tool's JSON result, or "ERROR: <message>" for a tool error.
With --value, a result with rows prints only the first column of the first row ("" if there are no rows,
NULL for a SQL NULL), so a test can compare it as a plain word.

Requests go one at a time: each waits for its reply before the next is sent, at most REPLY_TIMEOUT_S
seconds; after that the server is killed and this exits with an error.
The server runs as `python3 server/inventory_mcp.py` unless INVENTORY_SERVER_CMD overrides it
(the Postgres runner uses `uv run --script`, which brings psycopg). The environment is passed through.
"""
from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import sys
import threading
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "server" / "inventory_mcp.py"
REPLY_TIMEOUT_S = 30


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
    p = subprocess.Popen(cmd + [str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    # Read replies on a thread so a server that goes quiet can't hang the test: each reply has a deadline
    replies = queue.Queue()

    def pump():
        for ln in iter(p.stdout.readline, b""):
            replies.put(ln)
        replies.put(b"")  # EOF

    threading.Thread(target=pump, daemon=True).start()

    def rpc(msg):
        p.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        p.stdin.flush()
        if "id" not in msg:
            return None
        try:
            line = replies.get(timeout=REPLY_TIMEOUT_S)
        except queue.Empty:
            p.kill()
            sys.exit(f"server did not answer {msg.get('method')} within {REPLY_TIMEOUT_S}s; killed it")
        if not line:
            sys.exit(f"server exited without answering {msg.get('method')} (exit {p.wait()})")
        return json.loads(line.decode("utf-8"))

    rpc({"jsonrpc": "2.0", "id": 0, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "inventory-tests", "version": "0"}}})
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools = rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    if not calls:
        print(",".join(t["name"] for t in tools["result"]["tools"]))

    for i, (name, arguments) in enumerate(calls, start=2):
        query = arguments.get("query", "")
        if name == "execute_sql" and query.startswith("!"):
            try:
                subprocess.run(query[1:], shell=True, check=True, stdout=subprocess.DEVNULL, timeout=REPLY_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                sys.exit(f"external command did not finish within {REPLY_TIMEOUT_S}s: {query[1:]}")
            continue
        r = rpc({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                 "params": {"name": name, "arguments": arguments}})
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
    p.stdin.close()
    p.wait(timeout=60)


if __name__ == "__main__":
    main()
