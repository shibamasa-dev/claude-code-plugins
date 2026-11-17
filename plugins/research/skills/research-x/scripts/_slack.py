#!/usr/bin/env python3
"""Post to the Slack channel, and recover "how far the last run got" from that channel's history.

**The channel itself is the state.** Every run reads the history and, from bot posts in research-x format,
takes the start time of the previous run and the status IDs already posted. The run start time is stored in
each post's message metadata (`research_x_post`). A post without that metadata (posted by another tool in the
same format) is dated from its own timestamp minus RUN_OVERLAP, so it still counts.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://slack.com/api/"
TOKEN_ENV = "SLACK_BOT_TOKEN"
SEPARATOR = "----------------------------"
EVENT_TYPE = "research_x_post"
# For a post without metadata, how far before its timestamp the run is assumed to have started
RUN_OVERLAP = timedelta(minutes=15)
# The quoted URL at the end of a post. Sent as `>URL`; history returns `&gt;<URL>` or `&gt;<URL|label>`
QUOTED_STATUS = re.compile(r"(?:^|\n)(?:>|&gt;)\s*<?https?://(?:www\.)?(?:x|twitter)\.com/[A-Za-z0-9_]+/status/(\d+)")
MAX_RATE_LIMIT_RETRIES = 3


class SlackError(RuntimeError):
    """The Slack API returned ok: false, or a required setting is missing."""


def token(required: bool):
    value = os.environ.get(TOKEN_ENV, "").strip()
    if required and not value:
        raise SlackError(f"{TOKEN_ENV} is not set")
    return value or None


def escape(text: str) -> str:
    """Escape Slack control characters, so a summary containing `<!here>` can't notify the channel."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(post: dict) -> str:
    """Separator line, blank line, summary, then the status URL as a quote. Only the summary is escaped."""
    return f"{SEPARATOR}\n\n{escape(post['summary'])}\n>{post['url']}\n"


def quoted_status_id(message: dict):
    """The status ID a research-x post quotes, or None. Only bot posts that start with the separator count.

    Other X links inside the summary are ignored (counting them would mark posts not yet sent as posted).
    Any bot counts, so moving to another bot app keeps the previous posts.
    """
    text = message.get("text", "")
    if not message.get("bot_id") or not text.startswith(SEPARATOR):
        return None
    ids = QUOTED_STATUS.findall(text)
    return ids[-1] if ids else None


def run_started_at(message: dict) -> datetime:
    """Start time of the run that sent this post. Without metadata, estimated from the post's timestamp."""
    metadata = message.get("metadata") or {}
    if metadata.get("event_type") == EVENT_TYPE:
        started = (metadata.get("event_payload") or {}).get("run_started_at")
        if started:
            return datetime.fromisoformat(started)
    return datetime.fromtimestamp(float(message["ts"]), timezone.utc) - RUN_OVERLAP


def history_state(messages) -> dict:
    """Build {last_run_started_at, posted_ids} from history. The former is None when there are no research-x posts."""
    posts = [m for m in messages if quoted_status_id(m)]
    return {
        "last_run_started_at": max((run_started_at(m) for m in posts), default=None),
        "posted_ids": {quoted_status_id(m) for m in posts},
    }


def _call(method, tok, *, params=None, body=None, opener=None, sleep=time.sleep) -> dict:
    """Call the Slack Web API. On 429, wait for Retry-After and send the same request again."""
    opener = opener or urllib.request.urlopen
    url = API + method + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Authorization": f"Bearer {tok}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
        data = json.dumps(body).encode("utf-8")
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            with opener(urllib.request.Request(url, data=data, headers=headers), timeout=60) as resp:
                payload = json.load(resp)
            break
        except urllib.error.HTTPError as err:
            if err.code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
                raise SlackError(f"{method}: HTTP {err.code}") from err
            sleep(int(err.headers.get("Retry-After") or 1))
    if not payload.get("ok"):
        raise SlackError(f"{method}: {payload.get('error')}")
    return payload


def fetch_history(tok, oldest: datetime, *, channel: str, opener=None) -> list:
    """All messages since `oldest`, with metadata, following every page.

    Needs the channels:history scope (groups:history for a private channel), and the bot must be in the channel.
    """
    messages, cursor = [], None
    while True:
        params = {
            "channel": channel, "oldest": f"{oldest.timestamp():.6f}", "limit": 200,
            "include_all_metadata": "true",
        }
        if cursor:
            params["cursor"] = cursor
        page = _call("conversations.history", tok, params=params, opener=opener)
        messages.extend(page.get("messages", []))
        cursor = (page.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            return messages


def post(tok, text: str, run_started: datetime, *, channel: str, opener=None, sleep=time.sleep) -> str:
    """Post one message and return its ts. The run start time goes into metadata as the next run's cursor."""
    body = {
        "channel": channel, "text": text, "mrkdwn": True, "link_names": False,
        "metadata": {"event_type": EVENT_TYPE, "event_payload": {"run_started_at": run_started.isoformat()}},
    }
    return _call("chat.postMessage", tok, body=body, opener=opener, sleep=sleep)["ts"]
