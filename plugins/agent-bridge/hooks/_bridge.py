"""Shared helpers for the agent-bridge hooks: settings, the state directory and the unauthenticated status call.

Hooks get userConfig as CLAUDE_PLUGIN_OPTION_<KEY>. The status call needs no token: it returns counts only.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

AGENT_ID = re.compile(r"^[a-z0-9_-]{1,40}$")


def option(key: str) -> str:
    v = os.environ.get("CLAUDE_PLUGIN_OPTION_" + key.upper(), "").strip()
    return "" if v.startswith("${") else v


def config():
    """(status_url, agent_id), or None when the bridge is not set up on this machine."""
    url, agent = option("bridge_url"), option("agent_id")
    if not url or not AGENT_ID.match(agent):
        return None
    try:
        p = urllib.parse.urlsplit(url)
        ok = p.scheme == "https" and bool(p.hostname) or (p.scheme == "http" and p.hostname == "127.0.0.1")
    except ValueError:
        ok = False
    if not ok:  # https, or plain http to 127.0.0.1 only (a local test bridge); the host is parsed, not prefix-matched
        return None
    sep = "&" if "?" in url else "?"
    return url + sep + "agent=" + urllib.parse.quote(agent), agent


def status(status_url: str, timeout: float) -> dict:
    with urllib.request.urlopen(status_url, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {"unread": int(data.get("unread", 0)), "latest_id": int(data.get("latest_id", 0))}


def state_dir() -> Path:
    base = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    d = Path(base) / "wait" if base else Path.home() / ".claude" / "state" / "agent-bridge" / "wait"
    d.mkdir(parents=True, exist_ok=True)
    return d
