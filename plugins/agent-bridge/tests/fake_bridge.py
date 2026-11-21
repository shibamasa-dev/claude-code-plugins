#!/usr/bin/env python3
"""An in-memory stand-in for the bridge's Edge Function, for the MCP server and hook tests.

    fake_bridge.py PORTFILE

Listens on 127.0.0.1 (a free port, written to PORTFILE) and answers GET ?agent=<id> and POST {"action": ...}
with the response keys in fixtures/contract.json. Participants (all poll type) and their tokens come from
FAKE_BRIDGE_AGENTS, "id=token,id=token". FAKE_BRIDGE_DOWN=1 makes every request answer 503.
"""
import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

AGENTS = dict(p.split("=", 1) for p in os.environ.get("FAKE_BRIDGE_AGENTS", "").split(",") if "=" in p)
TOKENS = {tok: agent for agent, tok in AGENTS.items()}
MESSAGES = []
THREADS = {}
LOCK = threading.Lock()
MAX_MESSAGES = 3  # small, so the hop limit is easy to reach in a test


class Fail(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def now():
    return datetime.now(timezone.utc).isoformat()


def api(me, action, a):
    if action == "send":
        to, thread, body = a.get("to"), a.get("thread"), a.get("body")
        if not (to and thread and body):
            raise Fail(400, "bad_request", "send needs to, thread and body")
        if to not in AGENTS:
            raise Fail(400, "unknown_agent", f"no active participant {to}")
        THREADS.setdefault(thread, a.get("purpose", ""))
        if sum(1 for m in MESSAGES if m["thread"] == thread) >= MAX_MESSAGES:
            raise Fail(409, "hop_limit", f"thread {thread} already has {MAX_MESSAGES} messages")
        m = {"id": len(MESSAGES) + 1, "thread": thread, "from": me, "to": to, "body": body, "delivery": "poll",
             "created_at": now(), "claimed_at": None, "read_at": None}
        MESSAGES.append(m)
        return {"id": m["id"], "thread": thread, "to": to, "delivery": "poll"}
    if action == "inbox":
        out = []
        for m in MESSAGES:
            if m["to"] == me and m["read_at"] is None and m["claimed_at"] is None:
                m["claimed_at"] = now()
                out.append({"id": m["id"], "thread": m["thread"], "from": m["from"], "purpose": THREADS[m["thread"]],
                            "body": m["body"], "created_at": m["created_at"]})
        return {"agent": me, "messages": out}
    if action == "ack":
        n = 0
        for m in MESSAGES:
            if m["to"] == me and m["read_at"] is None and m["id"] in a.get("ids", []):
                m["read_at"] = now()
                n += 1
        return {"acked": n}
    if action == "participants":
        return {"me": me, "participants": [{"agent_id": k, "display_name": k, "role": "", "capabilities": "",
                                            "wake": "poll"} for k in sorted(AGENTS)]}
    if action == "message":
        for m in MESSAGES:
            if m["id"] == a.get("id") and me in (m["from"], m["to"]):
                return {k: m[k] for k in ("id", "thread", "from", "to", "delivery", "claimed_at", "read_at")}
        raise Fail(404, "not_found", "no such message")
    raise Fail(400, "bad_request", f"unknown action {action}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if os.environ.get("FAKE_BRIDGE_DOWN") == "1":
            return self.reply(503, {"error": "internal", "message": "down"})
        agent = (parse_qs(urlparse(self.path).query).get("agent") or [""])[0]
        with LOCK:
            mine = [m for m in MESSAGES if m["to"] == agent]
            self.reply(200, {"agent": agent, "unread": sum(1 for m in mine if m["read_at"] is None),
                             "latest_id": max((m["id"] for m in mine), default=0)})

    def do_POST(self):
        if os.environ.get("FAKE_BRIDGE_DOWN") == "1":
            return self.reply(503, {"error": "internal", "message": "down"})
        if os.environ.get("FAKE_BRIDGE_REDIRECT") == "1":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        auth = self.headers.get("Authorization", "")
        me = TOKENS.get(auth[7:]) if auth.startswith("Bearer ") else None
        if not me:
            return self.reply(401, {"error": "unauthorized", "message": "the token does not match any participant"})
        payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        action = payload.pop("action", "")
        try:
            with LOCK:
                self.reply(200, api(me, action, payload))
        except Fail as e:
            self.reply(e.status, {"error": e.code, "message": str(e)})


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    with open(sys.argv[1], "w") as f:
        f.write(str(srv.server_address[1]))
    srv.serve_forever()


if __name__ == "__main__":
    main()
