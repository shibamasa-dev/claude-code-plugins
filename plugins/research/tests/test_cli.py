#!/usr/bin/env python3
"""End-to-end tests of the CLI: settings, two runs in a row, first run, dry-run, failed fetch, missing key.

xAI replies come from a real API response (fixtures/xai_response.json, handles redacted) and one post seen in a
real dry-run. Status IDs in the fixtures and here are synthetic, with the real timestamp bits. Slack is a fake that keeps posted messages in memory and returns them
as history, so "the next run reads what the previous run posted" goes through the real code path.
Run: python3 tests/test_cli.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "research-x" / "scripts"))

import research_x  # noqa: E402

REAL_RESPONSE = json.loads((HERE / "fixtures" / "xai_response.json").read_text(encoding="utf-8"))
REAL_HISTORY = json.loads((HERE / "fixtures" / "slack_history.json").read_text(encoding="utf-8"))
REAL_POSTS = research_x._xai.parse_posts(REAL_RESPONSE)  # four posts, 2026-09-22 02:15Z to 18:00Z
NEW_POST = {  # posted 2026-09-23 01:00Z; from a real dry-run
    "url": "https://x.com/example_log/status/2102563629865541638",
    "posted_at": "2026-09-23T01:00:07Z",
    "summary": "GitHub Copilot for JetBrains 1.18.0リリース！AIアシスト承認や共有orgスキル、"
               "Codexエージェントのプランmode追加でめっちゃ進化してるよ〜 詳細リンクあり",
    "tags": ["product-update"],
}

# 25 handles: the three in the fixtures plus 22 others, so a run makes three requests of at most 10
ACCOUNTS = ["example_web", "example_ai", "example_log"] + [f"acct{i:02d}" for i in range(22)]
CHANNEL = "C0123456789"
ENV = {
    "XAI_API_KEY": "xai-test", "SLACK_BOT_TOKEN": "xoxb-test",
    "RESEARCH_X_ACCOUNTS": ", ".join(ACCOUNTS), "RESEARCH_X_SLACK_CHANNEL": CHANNEL,
    # Explicit, so the expected offsets below hold on any machine
    "RESEARCH_X_TIMEZONE": "Asia/Tokyo",
}
LATEST = "grok-4.7"  # newest generation in the real model list (fixtures/language_models.json)


def response(posts):
    return {"model": "grok-4.3", "status": "completed", "output": [{
        "type": "message",
        "content": [{"type": "output_text", "text": json.dumps({"posts": posts}, ensure_ascii=False)}],
    }]}


class FakeChannel:
    """Stands in for the Slack channel. What is posted is stored as a bot message in the history."""

    def fetch_history(self, tok, oldest, *, channel, **_):
        self.channels.add(channel)
        return [m for m in self.messages if float(m["ts"]) >= oldest.timestamp()]

    def __init__(self, messages=(), fail_on_post=None):
        self.messages = list(messages)
        self.clock = None
        self.channels = set()
        self.fail_on_post = fail_on_post  # 1-based number of the post that fails, counted over this channel's life
        self.attempts = 0

    def post(self, tok, text, run_started, *, since, last, channel, **_):
        self.channels.add(channel)
        self.attempts += 1
        if self.attempts == self.fail_on_post:
            raise research_x._slack.SlackError("chat.postMessage: HTTP 500")
        self.clock += timedelta(seconds=1)
        ts = f"{self.clock.timestamp():.6f}"
        payload = {"run_started_at": run_started.isoformat(), "since": since.isoformat()}
        if last:
            payload["last"] = True
        self.messages.append({
            "type": "message", "bot_id": "B0000000001", "ts": ts, "text": text,
            "metadata": {"event_type": "research_x_post", "event_payload": payload},
        })
        return ts


class FixedNow(datetime):
    """`datetime` whose now() is 2026-09-23 00:02 UTC, so the first-run window (24 h back) covers REAL_POSTS."""

    @classmethod
    def now(cls, tz=None):
        moment = datetime(2026, 9, 23, 0, 2, tzinfo=timezone.utc)
        return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)


def search_replies(posts):
    """The first chunk returns posts; the other two return none."""
    return [response(posts)] + [response([])] * 2


def run(channel, now, posts, argv=(), took=timedelta(minutes=2), env=ENV):
    """One run. `took` is how long fetching and summarizing takes."""
    channel.clock = now + took
    with patch.dict(os.environ, env, clear=True), \
         patch.object(research_x._slack, "fetch_history", channel.fetch_history), \
         patch.object(research_x._slack, "post", channel.post), \
         patch.object(research_x.time, "sleep"), \
         patch.object(research_x._xai, "latest_model", return_value=LATEST), \
         patch.object(research_x._xai, "search", side_effect=search_replies(posts)):
        return research_x.run(research_x.parse_args(list(argv)), now=now)


class SettingsTest(unittest.TestCase):
    def test_every_configured_account_is_searched_in_chunks_of_at_most_20(self):
        calls = []

        def search(handles, since, *, model, key, **_):
            calls.append({"handles": list(handles), "model": model})
            return response([])

        with patch.dict(os.environ, ENV, clear=True), \
             patch.object(research_x._slack, "fetch_history", FakeChannel().fetch_history), \
             patch.object(research_x._xai, "latest_model", return_value=LATEST), \
             patch.object(research_x._xai, "search", side_effect=search):
            report = research_x.run(research_x.parse_args([]), now=datetime(2026, 9, 23, tzinfo=timezone.utc))

        self.assertTrue(report["ok"], report)
        self.assertEqual([h for call in calls for h in call["handles"]], ACCOUNTS)
        self.assertTrue(all(len(call["handles"]) <= 20 for call in calls))
        self.assertEqual({call["model"] for call in calls}, {LATEST})

    def test_settings_reach_the_search(self):
        """Language, tone and topic from the settings are what the search is asked with."""
        seen = []

        def search(handles, since, *, model, key, topic, language, tone):
            seen.append((model, topic, language, tone, since.utcoffset()))
            return response([])

        env = {**ENV, "RESEARCH_X_MODEL": "grok-4.3", "RESEARCH_X_LANGUAGE": "Japanese",
               "RESEARCH_X_TONE": "casual", "RESEARCH_X_TOPIC": "- Only release notes"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(research_x._slack, "fetch_history", FakeChannel().fetch_history), \
             patch.object(research_x._xai, "latest_model") as latest, \
             patch.object(research_x._xai, "search", side_effect=search):
            research_x.run(research_x.parse_args([]), now=datetime(2026, 9, 23, tzinfo=timezone.utc))

        latest.assert_not_called()
        self.assertEqual(set(seen), {("grok-4.3", "- Only release notes", "Japanese", "casual", timedelta(hours=9))})

    def test_empty_accounts_fail_with_the_setting_name(self):
        env = {k: v for k, v in ENV.items() if k != "RESEARCH_X_ACCOUNTS"}

        report = run(FakeChannel(), datetime(2026, 9, 23, tzinfo=timezone.utc), [], env=env)

        self.assertFalse(report["ok"])
        self.assertIn("RESEARCH_X_ACCOUNTS", report["error"])

    def test_an_unsubstituted_placeholder_counts_as_empty(self):
        env = {**ENV, "RESEARCH_X_ACCOUNTS": "${user_config.accounts}"}

        report = run(FakeChannel(), datetime(2026, 9, 23, tzinfo=timezone.utc), [], env=env)

        self.assertFalse(report["ok"])
        self.assertIn("RESEARCH_X_ACCOUNTS", report["error"])

    def test_history_is_read_from_the_configured_channel(self):
        channel = FakeChannel()

        run(channel, datetime(2026, 9, 23, tzinfo=timezone.utc), REAL_POSTS)

        self.assertEqual(channel.channels, {CHANNEL})


class StateTest(unittest.TestCase):
    def test_second_run_only_posts_what_came_after_the_first(self):
        channel = FakeChannel()
        first = run(channel, datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc), REAL_POSTS)

        second = run(channel, datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc), REAL_POSTS + [NEW_POST])

        self.assertEqual(len(first["posts"]), 4)
        self.assertEqual([p["url"] for p in second["posts"]], [NEW_POST["url"]])
        self.assertEqual(second["since_source"], "slack_history")
        self.assertEqual(len(channel.messages), 5)

    def test_a_slow_run_does_not_lose_posts_published_while_it_was_searching(self):
        """A run that takes 50 minutes: the post made meanwhile (01:00Z) is picked up by the next run."""
        channel = FakeChannel()
        run(channel, datetime(2026, 9, 23, 0, 30, tzinfo=timezone.utc), REAL_POSTS, took=timedelta(minutes=50))

        second = run(channel, datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc), REAL_POSTS + [NEW_POST])

        self.assertEqual(second["since"], "2026-09-23T09:30:00+09:00")
        self.assertEqual([p["url"] for p in second["posts"]], [NEW_POST["url"]])

    def test_a_run_that_died_while_posting_is_completed_by_a_plain_retry(self):
        """Slack fails on the second post. The retry, with no options, sends the other three, nothing twice."""
        channel = FakeChannel(fail_on_post=2)
        failed = run(channel, datetime(2026, 9, 23, 0, 0, tzinfo=timezone.utc), REAL_POSTS)

        retry = run(channel, datetime(2026, 9, 23, 1, 0, tzinfo=timezone.utc), REAL_POSTS)

        self.assertFalse(failed["ok"])
        self.assertEqual(len(retry["posts"]), 3)
        self.assertEqual(retry["dropped"], {"already_posted": 1})
        quoted = [m["text"].rsplit("/", 1)[1].strip() for m in channel.messages]
        self.assertEqual(sorted(quoted), sorted(p["url"].rsplit("/", 1)[1] for p in REAL_POSTS))

    def test_a_retry_of_a_wide_run_reads_the_history_as_far_back_as_it_searches(self):
        """A run with --since-hours 240 died after one post. The plain retry searches its 240 h window again,
        so posts made 8 days earlier (outside the usual 7-day history read) must still count as posted."""
        died = {
            "type": "message", "bot_id": "B0000000001",
            "ts": f"{datetime(2026, 10, 1, 3, 5, tzinfo=timezone.utc).timestamp():.6f}",
            "text": f"----------------------------\n\nx\n&gt;<{NEW_POST['url']}>",
            "metadata": {"event_type": "research_x_post", "event_payload": {
                "run_started_at": "2026-10-01T03:00:00+00:00", "since": "2026-09-21T03:00:00+00:00"}},
        }
        channel = FakeChannel(REAL_HISTORY["messages"] + [died])  # four real posts from 2026-09-23 00:01Z

        report = run(channel, datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc), REAL_POSTS + [NEW_POST])

        self.assertEqual(report["since"], "2026-09-21T12:00:00+09:00")
        self.assertEqual(report["posts"], [])
        self.assertEqual(report["dropped"], {"already_posted": 5})

    def test_posts_already_in_the_channel_are_not_posted_again(self):
        """Posts older than the 7-day window are still skipped when --since-hours reaches back that far."""
        channel = FakeChannel(REAL_HISTORY["messages"])  # four real posts from 2026-09-23 00:01Z

        report = run(channel, datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc), REAL_POSTS, ["--since-hours", "240"])

        self.assertEqual(report["posts"], [])
        self.assertEqual(report["dropped"], {"already_posted": 4})
        self.assertEqual(len(channel.messages), 4)

    def test_first_run_looks_back_24_hours(self):
        """No research-x post in the channel means a first run. A post older than 24 hours (02:15Z) is skipped."""
        report = run(FakeChannel(), datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc), REAL_POSTS)

        self.assertTrue(report["history_read"])
        self.assertEqual(report["since_source"], "first_run")
        self.assertEqual(report["since"], "2026-09-22T12:00:00+09:00")
        self.assertEqual(report["dropped"], {"before_since": 1})


class SelectTest(unittest.TestCase):
    def test_status_urls_without_the_author_are_dropped(self):
        """`x.com/i/status/<id>` has no author, so it can't be confirmed as one of the accounts."""
        post = dict(REAL_POSTS[0], url="https://x.com/i/status/2102450622091141123")

        picked, dropped = research_x.select_posts(
            [post], datetime(2026, 9, 22, tzinfo=timezone.utc), set(), ACCOUNTS, timezone.utc)

        self.assertEqual(picked, [])
        self.assertEqual(dropped, {"other_account": 1})


class SafetyTest(unittest.TestCase):
    def test_dry_run_never_posts(self):
        channel = FakeChannel()
        with patch.object(research_x._slack, "post", side_effect=AssertionError("posted during --dry-run")) as post:
            report = run(channel, datetime(2026, 9, 23, 3, 0, tzinfo=timezone.utc), REAL_POSTS, ["--dry-run"])

        self.assertTrue(report["ok"], report)
        self.assertEqual(post.call_count, 0)
        self.assertEqual(len(report["posts"]), 3)
        self.assertTrue(report["posts"][0]["text"].startswith("----------------------------\n\n"))
        self.assertEqual(channel.messages, [])

    def test_a_failed_chunk_posts_nothing_and_exits_1(self):
        """If one chunk fails, nothing is posted (posting would move the cursor past the failed chunk's posts)."""
        channel = FakeChannel()
        channel.clock = datetime(2026, 9, 23, 0, 2, tzinfo=timezone.utc)
        failure = research_x._xai.XaiError("HTTP 503: upstream timeout")
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, ENV, clear=True), \
             patch.object(research_x, "datetime", FixedNow), \
             patch.object(research_x._slack, "fetch_history", channel.fetch_history), \
             patch.object(research_x._slack, "post", channel.post), \
             patch.object(research_x._xai, "latest_model", return_value=LATEST), \
             patch.object(research_x._xai, "search", side_effect=[response(REAL_POSTS), failure]), \
             redirect_stdout(out), redirect_stderr(err):
            code = research_x.main([])

        self.assertEqual(code, 1)
        self.assertEqual(channel.messages, [])
        result = json.loads(out.getvalue())
        self.assertIn("HTTP 503", result["error"])
        self.assertEqual(result["posted"], [])

    def test_missing_xai_key_exits_non_zero_and_names_the_variable(self):
        env = {k: v for k, v in ENV.items() if k != "XAI_API_KEY"}
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env, clear=True), \
             patch.object(research_x._slack, "fetch_history", FakeChannel().fetch_history), \
             patch.object(research_x._xai, "latest_model", side_effect=AssertionError("network call")), \
             patch.object(research_x._xai, "search", side_effect=AssertionError("network call")), \
             redirect_stdout(out), redirect_stderr(err):
            code = research_x.main(["--dry-run"])

        self.assertNotEqual(code, 0)
        self.assertIn("XAI_API_KEY", json.loads(err.getvalue())["error"])

    def test_posting_needs_the_slack_token(self):
        env = {k: v for k, v in ENV.items() if k != "SLACK_BOT_TOKEN"}

        report = run(FakeChannel(), datetime(2026, 9, 23, tzinfo=timezone.utc), REAL_POSTS, env=env)

        self.assertFalse(report["ok"])
        self.assertIn("SLACK_BOT_TOKEN", report["error"])


if __name__ == "__main__":
    unittest.main()
