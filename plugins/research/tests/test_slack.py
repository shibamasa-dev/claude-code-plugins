#!/usr/bin/env python3
"""Tests of the Slack side: message text, recovering state from history, API calls.

The text and ts in `fixtures/slack_history.json` are four real posts in research-x format (read through a Slack
connector; handles and the bot ID redacted). The `conversations.history` envelope around them (`bot_id`, the
`&gt;` and `<URL>` escaping) was assembled to match the Slack API documentation, so it is synthetic.
Run: python3 tests/test_slack.py
"""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "research-x" / "scripts"))

import _slack  # noqa: E402

HISTORY = json.loads((HERE / "fixtures" / "slack_history.json").read_text(encoding="utf-8"))
CHANNEL = "C0123456789"


class FakeOpener:
    """Stands in for urlopen. Keeps the requests and returns the prepared replies in order."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return io.BytesIO(json.dumps(payload).encode("utf-8"))


class FormatTest(unittest.TestCase):
    def test_message_is_separator_summary_and_quoted_url(self):
        text = _slack.format_message({
            "summary": "GitHub Copilot for JetBrains 1.18.0リリース！",
            "url": "https://x.com/example_log/status/2102563629866320156",
        })

        self.assertEqual(
            text,
            "----------------------------\n\n"
            "GitHub Copilot for JetBrains 1.18.0リリース！\n"
            ">https://x.com/example_log/status/2102563629866320156\n",
        )

    def test_summary_cannot_trigger_a_channel_mention(self):
        text = _slack.format_message({"summary": "<!here> R&D", "url": "https://x.com/example_web/status/1"})

        self.assertIn("&lt;!here&gt; R&amp;D\n>https://x.com/example_web/status/1", text)


class HistoryStateTest(unittest.TestCase):
    def test_state_is_recovered_from_real_channel_posts(self):
        """These posts carry no metadata, so the run is assumed to have started 15 minutes before the post."""
        state = _slack.history_state(HISTORY["messages"])

        self.assertEqual(
            state["since"],
            datetime.fromtimestamp(1790121716.948479, timezone.utc) - timedelta(minutes=15),
        )
        self.assertEqual(state["posted_ids"], {
            "2102450622092239171", "2102435517165912464", "2102457938086400425", "2102220114837795297",
        })

    def test_human_messages_do_not_count_as_posted(self):
        """A person pasting a link does not mark that post as already sent."""
        human = dict(HISTORY["messages"][0])
        del human["bot_id"]

        self.assertEqual(_slack.history_state([human]), {"since": None, "posted_ids": set()})

    def test_run_start_comes_from_metadata(self):
        message = dict(HISTORY["messages"][0], metadata={
            "event_type": "research_x_post",
            "event_payload": {"run_started_at": "2026-09-24T00:00:00+00:00", "last": True},
        })

        self.assertEqual(
            _slack.history_state([message])["since"],
            datetime(2026, 9, 24, tzinfo=timezone.utc),
        )

    def test_an_unfinished_run_restarts_from_its_own_window(self):
        """The latest run has no post marked last: it died midway, so the next search reuses its window."""
        def sent(status_id, started, since, last=False):
            payload = {"run_started_at": started, "since": since, **({"last": True} if last else {})}
            return dict(HISTORY["messages"][0], text=f"{_slack.SEPARATOR}\n\ns\n&gt;<https://x.com/example_web/status/{status_id}>",
                        metadata={"event_type": "research_x_post", "event_payload": payload})

        finished = sent("1", "2026-09-23T00:00:00+00:00", "2026-09-22T00:00:00+00:00", last=True)
        died = sent("2", "2026-09-24T00:00:00+00:00", "2026-09-23T00:00:00+00:00")

        self.assertEqual(_slack.history_state([finished])["since"], datetime(2026, 9, 23, tzinfo=timezone.utc))
        self.assertEqual(_slack.history_state([finished, died])["since"], datetime(2026, 9, 23, tzinfo=timezone.utc))

    def test_links_inside_the_summary_are_not_counted_as_posted(self):
        """A summary that mentions another X post has not posted that post."""
        message = dict(HISTORY["messages"][0], text=(
            "----------------------------\n\n"
            "前回の告知 https://x.com/example_web/status/2102000000000000000 の続報だよ〜\n"
            "&gt;<https://x.com/example_web/status/2102450622092239171|x.com/example_web/status/2102450622092239171>"
        ))

        self.assertEqual(_slack.history_state([message])["posted_ids"], {"2102450622092239171"})


class ApiTest(unittest.TestCase):
    def test_history_follows_the_cursor_on_the_given_channel(self):
        first, second = HISTORY["messages"][:2], HISTORY["messages"][2:]
        opener = FakeOpener(
            {"ok": True, "messages": first, "response_metadata": {"next_cursor": "bmV4dA=="}},
            {"ok": True, "messages": second, "response_metadata": {"next_cursor": ""}},
        )

        messages = _slack.fetch_history("xoxb-test", datetime(2026, 9, 16, tzinfo=timezone.utc),
                                        channel=CHANNEL, opener=opener)

        self.assertEqual(len(messages), 4)
        self.assertIn(f"channel={CHANNEL}", opener.requests[0].full_url)
        self.assertIn("cursor=bmV4dA%3D%3D", opener.requests[1].full_url)

    def test_not_in_channel_is_an_error(self):
        """If the bot is not in the channel, the history can't be read. Treating it as empty would post everything again."""
        opener = FakeOpener({"ok": False, "error": "not_in_channel"})

        with self.assertRaises(_slack.SlackError):
            _slack.fetch_history("xoxb-test", datetime(2026, 9, 16, tzinfo=timezone.utc),
                                 channel=CHANNEL, opener=opener)

    def test_post_sends_the_text_options_and_the_run_start(self):
        opener = FakeOpener({"ok": True, "ts": "1790200000.000100"})

        ts = _slack.post("xoxb-test", "本文", datetime(2026, 9, 24, tzinfo=timezone.utc),
                         since=datetime(2026, 9, 23, tzinfo=timezone.utc), last=True, channel=CHANNEL, opener=opener)

        body = json.loads(opener.requests[0].data)
        self.assertEqual(ts, "1790200000.000100")
        self.assertEqual(body, {
            "channel": CHANNEL, "text": "本文", "mrkdwn": True, "link_names": False,
            "metadata": {"event_type": "research_x_post",
                         "event_payload": {"run_started_at": "2026-09-24T00:00:00+00:00",
                                           "since": "2026-09-23T00:00:00+00:00", "last": True}},
        })

    def test_rate_limited_post_waits_for_retry_after(self):
        limited = urllib.error.HTTPError(_slack.API, 429, "Too Many Requests", {"Retry-After": "3"}, io.BytesIO(b""))
        opener = FakeOpener(limited, {"ok": True, "ts": "1790200001.000100"})
        waited = []

        ts = _slack.post("xoxb-test", "本文", datetime(2026, 9, 24, tzinfo=timezone.utc),
                         since=datetime(2026, 9, 23, tzinfo=timezone.utc), last=False,
                         channel=CHANNEL, opener=opener, sleep=waited.append)

        self.assertEqual(ts, "1790200001.000100")
        self.assertEqual(waited, [3])


if __name__ == "__main__":
    unittest.main()
