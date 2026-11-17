#!/usr/bin/env python3
"""Tests of the xAI side: request shape, reading the reply, post time from the status ID.

`fixtures/xai_response.json` is a real Responses API reply (x_search over three accounts) with the reasoning
removed and the handles redacted. `fixtures/language_models.json` is a real model list.
The shape is from real output; status IDs and response / call IDs are synthetic (status IDs keep the
real timestamp bits, so the time decoded from them is unchanged).
Run: python3 tests/test_xai.py
"""

from __future__ import annotations

import http.client
import io
import json
import sys
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "skills" / "research-x" / "scripts"))

import _xai  # noqa: E402

TOKYO = ZoneInfo("Asia/Tokyo")
RESPONSE = json.loads((HERE / "fixtures" / "xai_response.json").read_text(encoding="utf-8"))
MODELS = json.loads((HERE / "fixtures" / "language_models.json").read_text(encoding="utf-8"))
MODEL = "grok-4.7"
SETTINGS = {"topic": "- Only release notes", "language": "Japanese", "tone": "casual"}


def body(handles=("example_web",), since=datetime(2026, 9, 23, 8, 46, 56, tzinfo=TOKYO)):
    return _xai.request_body(list(handles), since, MODEL, **SETTINGS)


class RequestTest(unittest.TestCase):
    def test_from_date_is_the_utc_date_of_since(self):
        """08:46 at UTC+9 is the previous day in UTC. Sending the local date would miss posts late that UTC day."""
        tools = body(["example_web", "example_ai"])["tools"]

        self.assertEqual(tools[0]["from_date"], "2026-09-22")
        self.assertEqual(tools[0]["allowed_x_handles"], ["example_web", "example_ai"])

    def test_prompt_carries_the_settings_and_since_with_its_offset(self):
        prompt = body()["input"][0]["content"]

        self.assertIn("- Only release notes", prompt)
        self.assertIn("Japanese", prompt)
        self.assertIn("casual", prompt)
        self.assertIn("2026-09-23 08:46:56 (UTC+09:00)", prompt)

    def test_request_uses_x_search_and_a_strict_schema(self):
        request = body()
        schema = request["text"]["format"]

        self.assertEqual(request["model"], MODEL)
        self.assertEqual([t["type"] for t in request["tools"]], ["x_search"])
        self.assertEqual(schema["type"], "json_schema")
        self.assertTrue(schema["strict"])
        self.assertEqual(set(schema["schema"]["properties"]["posts"]["items"]["properties"]),
                         {"url", "posted_at", "summary", "tags"})

    def test_reasoning_is_low_and_search_is_required(self):
        """With low effort alone the model sometimes skipped x_search, so the tool is required."""
        request = body()

        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertEqual(request["tool_choice"], "required")

    def test_search_posts_to_the_responses_endpoint(self):
        opener = Opener(RESPONSE)

        _xai.search(["example_web"], datetime(2026, 9, 23, tzinfo=TOKYO), model=MODEL, key="k",
                    opener=opener, **SETTINGS)

        self.assertEqual(opener.requests[0].full_url, "https://api.x.ai/v1/responses")
        self.assertEqual(opener.requests[0].get_method(), "POST")


class ParseTest(unittest.TestCase):
    def test_posts_come_from_the_message_output_text(self):
        posts = _xai.parse_posts(RESPONSE)

        self.assertEqual(
            [p["url"] for p in posts],
            [
                "https://x.com/example_web/status/2102450622091141123",
                "https://x.com/example_log/status/2102220114837020672",
                "https://x.com/example_ai/status/2102435517165117441",
                "https://x.com/example_log/status/2102457938085584900",
            ],
        )

    def test_response_without_message_is_an_error(self):
        """A reply cut off after the tool calls (status=incomplete and the like) is not an empty result."""
        cut = {"status": "incomplete", "output": [o for o in RESPONSE["output"] if o["type"] != "message"]}

        with self.assertRaises(_xai.XaiError):
            _xai.parse_posts(cut)


class Opener:
    """Stands in for urlopen. Returns the prepared results (an exception or a reply dict) in order."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    @property
    def calls(self):
        return len(self.requests)

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(json.dumps(result).encode("utf-8"))


class LatestModelTest(unittest.TestCase):
    def test_picks_the_newest_plain_generation_from_the_real_list(self):
        """The real list also has dated, reasoning, build and multi-agent variants; only plain names count."""
        opener = Opener(MODELS)

        self.assertEqual(_xai.latest_model("k", opener=opener), "grok-4.7")
        self.assertEqual(opener.requests[0].full_url, "https://api.x.ai/v1/language-models")

    def test_a_list_without_plain_generations_is_an_error(self):
        only_variants = {"models": [m for m in MODELS["models"] if m["id"].count("-") > 1]}

        with self.assertRaises(_xai.XaiError):
            _xai.latest_model("k", opener=Opener(only_variants))


class SearchTest(unittest.TestCase):
    SINCE = datetime(2026, 9, 22, 11, 39, tzinfo=TOKYO)

    def search(self, opener):
        return _xai.search(["example_web"], self.SINCE, model="m", key="k", opener=opener, retry_wait=0, **SETTINGS)

    def test_a_cut_response_is_retried_once(self):
        """A cut connection like one seen in a real dry-run."""
        opener = Opener(http.client.IncompleteRead(b"x" * 5664, 1014), RESPONSE)

        result = self.search(opener)

        self.assertEqual(result["model"], "grok-4.3")
        self.assertEqual(opener.calls, 2)

    def test_an_incomplete_response_is_not_accepted(self):
        """Even with HTTP 200, a status other than completed is a partial result. Fail if the retry is the same."""
        cut = dict(RESPONSE, status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        opener = Opener(cut, cut)

        with self.assertRaises(_xai.XaiError):
            self.search(opener)
        self.assertEqual(opener.calls, 2)

    def test_client_errors_are_not_retried(self):
        denied = urllib.error.HTTPError(
            _xai.API_URL, 401, "Unauthorized", None, io.BytesIO(b'{"error":"Incorrect API key provided"}'),
        )
        opener = Opener(denied)

        with self.assertRaises(_xai.XaiError):
            self.search(opener)
        self.assertEqual(opener.calls, 1)


class StatusIdTest(unittest.TestCase):
    def test_posted_at_is_recovered_from_the_status_id(self):
        """Matches the posted_at the API returned for the same post (2026-09-22T17:31:04Z)."""
        self.assertEqual(
            _xai.posted_at_from_id("2102450622091141123").replace(microsecond=0),
            datetime(2026, 9, 22, 17, 31, 4, tzinfo=timezone.utc),
        )

    def test_status_url_accepts_twitter_domain(self):
        self.assertEqual(
            _xai.parse_status_url("https://twitter.com/example_dev/status/2102442213203681282"),
            ("example_dev", "2102442213203681282"),
        )


if __name__ == "__main__":
    unittest.main()
