#!/usr/bin/env python3
"""Fetch posts from the given X accounts through the xAI Responses API (`x_search`) and return them summarized.

`x_search` takes `from_date` as a whole day, so "only posts since the last run" is not guaranteed by the API.
The caller (research_x.py) enforces it with the post time recovered from each status ID.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_URL = "https://api.x.ai/v1/responses"
MODELS_URL = "https://api.x.ai/v1/language-models"
# The model is picked from the model list on every run. xAI has no alias that follows the newest generation
# (aliases such as `grok-4.3-latest` stay within one generation, and some generations have none).
# Only plain `grok-<version>` names count; dated, reasoning / non-reasoning, build and multi-agent variants don't.
MODEL_FAMILY = re.compile(r"^grok-\d+(?:\.\d+)*$")
# Reasoning can't be turned off, so keep it at the minimum.
REASONING_EFFORT = "low"
# With low effort the model sometimes answers without calling x_search at all; require the tool.
TOOL_CHOICE = "required"
TEMPERATURE = 0.7

TAGS = [
    "product-update", "research", "corporate", "marketing", "support", "security",
    "content", "industry-trend", "data-insights", "open-source", "ai-ml", "community",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "posted_at": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["url", "posted_at", "summary", "tags"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["posts"],
    "additionalProperties": False,
}

PROMPT_TEMPLATE = """# Task: collect X posts

## Role
You collect posts that match the conditions below, analyze them, and return structured data to a downstream system.

## Input

### What to collect
{topic}

### Tag list
{tags}

### Posted at or after
{since}

## Task
Extract the posts that match "What to collect" and were posted at or after {since}, and output them in the format below, one entry per topic.
Summarize each post in about 300 characters or fewer, but don't make it too short.

## Output format (strict)

**Important**: answer with pure JSON only. No explanations, comments or code fences.

{{
  "posts": [
    {{
      "url": "https://x.com/username/status/123456789",
      "posted_at": "2025-06-06T09:06:57Z",
      "summary": "summary of the post",
      "tags": ["tags from the tag list that match the post"]
    }}
  ]
}}

### Fields
| Field | Meaning |
|-------|---------|
| `posts` | Array of extracted posts |
| `posts[].url` | URL of the post |
| `posts[].posted_at` | When it was posted (ISO 8601) |
| `posts[].summary` | Summary of the post in {language} (about 300 characters or fewer) |
| `posts[].tags` | Tags chosen from the tag list |

## Notes
- Skip a post whose parent post is not from one of the searched accounts.
- Aim for complete, useful information.
- Write `summary` in {language}. Tone: {tone}.
- When posts form a thread (a parent and replies chained under it), merge the replies into the parent and output only the parent. Example:

[Thread]
- Parent (ID: 1800000000000000001, URL: https://x.com/example_dev/status/1800000000000000001):
  Content: Example Tool 2.0 is out. It adds plugins that teach the tool your way of working.
  - Reply 1 (to the parent, ID: 1800000000000000002):
    Content: Plugins work in the desktop app, the CLI and the API, and can be combined.
    - Reply 2 (to reply 1, ID: 1800000000000000003):
      Content: Turn them on in Settings > Plugins. Available today on all paid plans. Details: https://example.com/news/plugins

[Merged output]
{{
  "url": "https://x.com/example_dev/status/1800000000000000001",
  "posted_at": "2025-10-16T16:07:55Z",
  "summary": "Example Tool 2.0 adds plugins that teach it your way of working. They work in the desktop app, the CLI and the API and can be combined. Turn them on in Settings > Plugins; available on all paid plans. Details: https://example.com/news/plugins",
  "tags": ["product-update"]
}}
"""

STATUS_URL = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)")
# An X status ID is a snowflake: its high bits are milliseconds since the Twitter epoch.
TWITTER_EPOCH_MS = 1288834974657


class XaiError(RuntimeError):
    """xAI returned a non-2xx status, or no posts JSON could be read from the response."""


def api_key() -> str:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        raise XaiError("XAI_API_KEY is not set")
    return key


def format_since(since: datetime) -> str:
    """`YYYY-MM-DD HH:MM:SS (UTC+hh:mm)` in the configured timezone, so the model sees the offset."""
    offset = since.strftime("%z")
    return f"{since.strftime('%Y-%m-%d %H:%M:%S')} (UTC{offset[:3]}:{offset[3:]})"


def build_prompt(since: datetime, *, topic: str, language: str, tone: str) -> str:
    return PROMPT_TEMPLATE.format(
        topic=topic,
        tags=json.dumps(TAGS, ensure_ascii=False),
        since=format_since(since),
        language=language,
        tone=tone,
    )


def request_body(handles, since: datetime, model: str, *, topic: str, language: str, tone: str) -> dict:
    return {
        "model": model,
        "input": [{"role": "user", "content": build_prompt(since, topic=topic, language=language, tone=tone)}],
        "tools": [{
            "type": "x_search",
            "allowed_x_handles": list(handles),
            # A whole day. The UTC date is never later than `since` in any timezone
            "from_date": since.astimezone(timezone.utc).strftime("%Y-%m-%d"),
        }],
        "text": {"format": {"type": "json_schema", "name": "posts", "schema": SCHEMA, "strict": True}},
        "temperature": TEMPERATURE,
        "reasoning": {"effort": REASONING_EFFORT},
        "tool_choice": TOOL_CHOICE,
    }


def latest_model(key: str, opener=None) -> str:
    """Return the plain generation name (such as `grok-4.7`) with the newest release date (`created`)."""
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {key}"})
    try:
        with opener(req, timeout=30) as resp:
            models = json.load(resp).get("models", [])
    except urllib.error.HTTPError as err:
        raise XaiError(f"model list HTTP {err.code}: {err.read().decode('utf-8', 'replace')[:300]}") from err
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError) as err:
        raise XaiError(f"model list {type(err).__name__}: {err}") from err
    family = [m for m in models if MODEL_FAMILY.match(m.get("id", ""))]
    if not family:
        raise XaiError(f"no grok-<version> in the model list: {[m.get('id') for m in models]}")
    return max(family, key=lambda m: m.get("created", 0))["id"]


def parse_posts(response: dict) -> list:
    """Take the posts array from a Responses API reply (the last message's output_text is the JSON)."""
    texts = [
        part.get("text", "")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    if not texts:
        raise XaiError(f"no output_text (status={response.get('status')})")
    try:
        return json.loads(texts[-1])["posts"]
    except (ValueError, KeyError, TypeError) as err:
        raise XaiError(f"cannot read posts JSON: {texts[-1][:200]}") from err


def search(handles, since: datetime, *, model: str, key: str, topic: str, language: str, tone: str,
           opener=None, retry_wait=10) -> dict:
    """Query one chunk and return the response JSON as is.

    A cut connection, a 5xx, or a response whose `status` is not `completed` is retried once.
    A 4xx (wrong key, bad request) won't get better on retry, so it fails right away.
    """
    opener = opener or urllib.request.urlopen
    body = request_body(handles, since, model, topic=topic, language=language, tone=tone)
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in (1, 2):
        try:
            with opener(req, timeout=300) as resp:
                result = json.load(resp)
            if result.get("status") == "completed":
                return result
            # `incomplete` and the like are partial results even with HTTP 200. Posting them would lose the rest
            if attempt == 2:
                raise XaiError(f"status={result.get('status')}: {result.get('incomplete_details')}")
        except urllib.error.HTTPError as err:
            if err.code < 500 or attempt == 2:
                raise XaiError(f"HTTP {err.code}: {err.read().decode('utf-8', 'replace')[:300]}") from err
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError) as err:
            if attempt == 2:
                raise XaiError(f"{type(err).__name__}: {err}") from err
        time.sleep(retry_wait)


def parse_status_url(url: str):
    """Return (handle, status_id), or None if it is not a status URL."""
    match = STATUS_URL.search(url or "")
    return (match.group(1), match.group(2)) if match else None


def posted_at_from_id(status_id: str) -> datetime:
    """Recover the post time from the status ID. The model's `posted_at` varies in format, so it isn't used."""
    return datetime.fromtimestamp(((int(status_id) >> 22) + TWITTER_EPOCH_MS) / 1000, timezone.utc)
