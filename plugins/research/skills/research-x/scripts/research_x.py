#!/usr/bin/env python3
"""research-x: summarize update announcements from a list of X accounts and post them to a Slack channel.

Flow:
  1. Recover the previous run's start time and the status IDs already posted from the channel history
     (the channel is the state; nothing is stored on disk)
  2. Ask xAI (x_search) about the accounts, 10 per request
  3. Keep posts made since the previous run (time recovered from the status ID), minus IDs already posted
  4. Post them oldest first, one message per post (--dry-run prints the text instead)

Settings come from environment variables (the skill sets them from the plugin's userConfig):
  RESEARCH_X_ACCOUNTS       comma-separated X handles (required)
  RESEARCH_X_SLACK_CHANNEL  Slack channel ID (required to post or to read history)
  RESEARCH_X_LANGUAGE       summary language (default: English)
  RESEARCH_X_TONE           summary tone (default: neutral and factual)
  RESEARCH_X_TOPIC          what counts as an update announcement (default: DEFAULT_TOPIC)
  RESEARCH_X_TIMEZONE       IANA timezone for times in the prompt and the report (default: system local)
  RESEARCH_X_MODEL          xAI model (default: the newest grok-<version> in the model list)
Credentials, also from the environment (never from userConfig):
  XAI_API_KEY               xAI API key (required)
  SLACK_BOT_TOKEN           Slack bot token with chat:write and channels:history (required unless --dry-run)

Usage:
    python3 research_x.py --dry-run                   # fetch and summarize, don't post
    python3 research_x.py --dry-run --since-hours 72  # choose how far back to look
    python3 research_x.py                             # post to Slack

Exit code: 0 = success, 1 = failure. If any xAI chunk fails, nothing is posted, so the next run
starts from the same point.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import _slack
import _xai

DEFAULT_LANGUAGE = "English"
DEFAULT_TONE = "neutral and factual"
DEFAULT_TOPIC = (
    "- Announcements of new or changed application features\n"
    "- No research results or papers\n"
    "- Only clear update announcements"
)
CHUNK_SIZE = 10  # within x_search's limit of 20 allowed_x_handles per request
FIRST_RUN_LOOKBACK = timedelta(hours=24)  # when the history has no research-x post
HISTORY_WINDOW = timedelta(days=7)  # how far back to look for the previous run (longer if --since-hours asks)
POST_INTERVAL_SECONDS = 1  # chat.postMessage allows roughly one message per second per channel
HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class ConfigError(RuntimeError):
    """A setting is missing or invalid."""


def setting(name: str) -> str:
    """An environment value, treating an unsubstituted `${user_config.…}` placeholder as empty."""
    value = os.environ.get(name, "").strip()
    return "" if value.startswith("${user_config.") else value


def parse_accounts(raw: str) -> list:
    handles = [h.strip().lstrip("@") for h in re.split(r"[,\s]+", raw) if h.strip().lstrip("@")]
    if not handles:
        raise ConfigError("RESEARCH_X_ACCOUNTS is empty: set the plugin's accounts option (comma-separated X handles)")
    bad = [h for h in handles if not HANDLE.match(h)]
    if bad:
        raise ConfigError(f"RESEARCH_X_ACCOUNTS has invalid X handles: {bad}")
    return list(dict.fromkeys(handles))


def load_config(opts) -> dict:
    tz_name = setting("RESEARCH_X_TIMEZONE")
    try:
        tz = ZoneInfo(tz_name) if tz_name else datetime.now().astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise ConfigError(f"RESEARCH_X_TIMEZONE is not a known IANA timezone: {tz_name!r}") from err
    return {
        "accounts": parse_accounts(setting("RESEARCH_X_ACCOUNTS")),
        "channel": setting("RESEARCH_X_SLACK_CHANNEL"),
        "language": setting("RESEARCH_X_LANGUAGE") or DEFAULT_LANGUAGE,
        "tone": setting("RESEARCH_X_TONE") or DEFAULT_TONE,
        "topic": setting("RESEARCH_X_TOPIC") or DEFAULT_TOPIC,
        "tz": tz,
        "model": opts.model or setting("RESEARCH_X_MODEL"),
    }


def chunks(items, size=CHUNK_SIZE):
    return [list(items[i:i + size]) for i in range(0, len(items), size)]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Summarize update announcements from X accounts and post them to Slack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="fetch and summarize, but don't post to Slack")
    parser.add_argument(
        "--since-hours", type=float, metavar="H",
        help="look back H hours instead of using the previous run's start time (posted IDs are still skipped)",
    )
    parser.add_argument("--model", help="xAI model (default: RESEARCH_X_MODEL, else the newest grok-<version>)")
    return parser.parse_args(argv)


def resolve_since(opts, state, now):
    """Return (since, where it came from)."""
    if opts.since_hours is not None:
        return now - timedelta(hours=opts.since_hours), "since_hours"
    if state["last_run_started_at"] is not None:
        return state["last_run_started_at"], "slack_history"
    return now - FIRST_RUN_LOOKBACK, "first_run"


def select_posts(raw_posts, since, posted_ids, accounts, tz):
    """The posts to send, oldest first, plus a count per reason for the ones dropped."""
    allowed = {a.lower() for a in accounts}
    picked, seen, dropped = [], set(), {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for post in raw_posts:
        parsed = _xai.parse_status_url(post.get("url", ""))
        if not parsed:
            drop("not_a_status_url")
            continue
        handle, status_id = parsed
        if handle.lower() not in allowed:
            # `x.com/i/status/<id>` has no author, so it can't be confirmed as one of the accounts
            drop("other_account")
        elif status_id in posted_ids:
            drop("already_posted")
        elif status_id in seen:
            drop("duplicate_in_run")
        elif _xai.posted_at_from_id(status_id) < since:
            drop("before_since")
        else:
            seen.add(status_id)
            picked.append({
                "url": f"https://x.com/{handle}/status/{status_id}",
                "status_id": status_id,
                "posted_at": _xai.posted_at_from_id(status_id).astimezone(tz).isoformat(),
                "summary": post.get("summary", "").strip(),
            })
    picked.sort(key=lambda p: int(p["status_id"]))
    return picked, dropped


def run(opts, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    report = {"ok": True, "dry_run": bool(opts.dry_run), "posts": []}
    try:
        cfg = load_config(opts)
        tz, model = cfg["tz"], cfg["model"]
        report.update({"model": model or None, "accounts": len(cfg["accounts"]),
                       "run_started_at": now.astimezone(tz).isoformat()})
        slack_token = _slack.token(required=not opts.dry_run)
        if not opts.dry_run and not cfg["channel"]:
            raise ConfigError("RESEARCH_X_SLACK_CHANNEL is empty: set the plugin's slack_channel option")
        state = {"last_run_started_at": None, "posted_ids": set()}
        history_read = bool(slack_token and cfg["channel"])
        if history_read:
            # Look as far back for posted IDs as for posts, so a wide --since-hours doesn't post twice
            oldest = now - max(HISTORY_WINDOW, timedelta(hours=opts.since_hours or 0))
            state = _slack.history_state(_slack.fetch_history(slack_token, oldest, channel=cfg["channel"]))
        else:
            report["warning"] = (f"{_slack.TOKEN_ENV} or RESEARCH_X_SLACK_CHANNEL is not set, so the history "
                                 "was not read (posts already in the channel are not skipped)")
        since, source = resolve_since(opts, state, now)
        report.update({"history_read": history_read, "since": since.astimezone(tz).isoformat(),
                       "since_source": source, "posted_ids_in_history": len(state["posted_ids"])})

        key = _xai.api_key()
        if not model:
            model = report["model"] = _xai.latest_model(key)
        raw_posts, resolved = [], set()
        for handles in chunks(cfg["accounts"]):
            response = _xai.search(handles, since.astimezone(tz), model=model, key=key,
                                   topic=cfg["topic"], language=cfg["language"], tone=cfg["tone"])
            resolved.add(response.get("model"))
            raw_posts.extend(_xai.parse_posts(response))
        report["resolved_models"] = sorted(m for m in resolved if m)
        report["fetched"] = len(raw_posts)

        picked, report["dropped"] = select_posts(raw_posts, since, state["posted_ids"], cfg["accounts"], tz)
        for i, post in enumerate(picked):
            text = _slack.format_message(post)
            record = {**post, "text": text}
            if not opts.dry_run:
                if i:
                    time.sleep(POST_INTERVAL_SECONDS)
                # Store the run start (now): if this run dies midway, the next one searches again from here
                # and skips what was already posted by ID
                record["ts"] = _slack.post(slack_token, text, now, channel=cfg["channel"])
            report["posts"].append(record)
    except Exception as err:  # noqa: BLE001 — wherever it fails, report the reason as JSON
        report["ok"] = False
        report["error"] = f"{type(err).__name__}: {err}"
    return report


def main(argv=None) -> int:
    """A real run prints the result JSON to stdout. --dry-run prints the post texts to stdout and the JSON to stderr."""
    opts = parse_args(argv)
    report = run(opts)
    summary = {k: v for k, v in report.items() if k != "posts"}
    summary["would_post" if opts.dry_run else "posted"] = [p["url"] for p in report["posts"]]
    if opts.dry_run:
        for post in report["posts"]:
            print(post["text"])
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr if opts.dry_run else sys.stdout)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
