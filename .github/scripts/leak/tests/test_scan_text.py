#!/usr/bin/env python3
"""Tests for scan-text.py and leak_patterns.py.

Run: python3 -m unittest discover -s .github/scripts/leak/tests

scan-text.py runs as a subprocess against a fake GitHub API on localhost (real HTTP, so paging and the
label write go through the same code as in CI). The field names in the fake responses are the ones the
real API returns (issue: number / title / body / user.type / labels[].name / pull_request; comments:
id / body / user / issue_url / pull_request_url; reviews: id / body / user).

The blocked names are made up (acme-internal). Home paths are built at run time so this file does not
trip check-repo.py's own scan.
"""
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scan-text.py")
WORKFLOW = os.path.join(HERE, "..", "..", "..", "workflows", "text-scan.yml")
sys.path.insert(0, os.path.join(HERE, ".."))
import leak_patterns  # noqa: E402

BLOCKED_NAME = "acme-internal"
HOME_PATH = "/Us" + "ers/" + "builder/work"   # matches the built-in home-path pattern
HUMAN = {"login": "octo", "type": "User"}
BOT = {"login": "review-bot[bot]", "type": "Bot"}
REPO = "acme/widgets"


class FakeApi:
    """Serves GET from `routes` (path -> JSON) and records label POSTs. A list value in `paged` is
    served one element per page with a Link header."""

    def __init__(self, routes, paged=(), read_only=False):
        self.routes, self.paged, self.read_only = routes, set(paged), read_only
        self.posts, self.gets = [], []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, link=None):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                if link:
                    self.send_header("Link", link)
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                path, _, query = self.path.partition("?")
                fake.gets.append(self.path)
                key = path[len(f"/repos/{REPO}"):]
                if key not in fake.routes:
                    return self._send(404, {"message": "Not Found"})
                body = fake.routes[key]
                if key in fake.paged:
                    m = re.search(r"(?:^|&)page=(\d+)", query)
                    page = int(m.group(1)) if m else 1
                    link = None
                    if page < len(body):
                        link = f'<http://127.0.0.1:{fake.port}{path}?per_page=100&page={page + 1}>; rel="next"'
                    return self._send(200, body[page - 1:page], link)
                self._send(200, body)

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if fake.read_only:
                    return self._send(403, {"message": "Resource not accessible by integration"})
                fake.posts.append((self.path, payload))
                self._send(200, [])

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def issue(n, title="Fix the build", body="Nothing to see", user=HUMAN, labels=(), pr=False):
    d = {"number": n, "title": title, "body": body, "user": user, "labels": [{"name": x} for x in labels]}
    if pr:
        d["pull_request"] = {"url": f"https://api.github.com/repos/{REPO}/pulls/{n}"}
    return d


def routes_for(item, comments=(), reviews=(), review_comments=()):
    n = item["number"]
    r = {f"/issues/{n}": item, f"/issues/{n}/comments": list(comments)}
    if "pull_request" in item:
        r[f"/pulls/{n}/reviews"] = list(reviews)
        r[f"/pulls/{n}/comments"] = list(review_comments)
    return r


class ScanTextTest(unittest.TestCase):
    def run_scan(self, event_name, event, routes, patterns=BLOCKED_NAME, **fake_kw):
        fake = FakeApi(routes, **fake_kw)
        self.addCleanup(fake.close)
        tmp = tempfile.mkdtemp()
        event_path, summary = os.path.join(tmp, "event.json"), os.path.join(tmp, "summary.md")
        with open(event_path, "w", encoding="utf-8") as f:
            json.dump(event, f)
        env = {"PATH": os.environ["PATH"], "GITHUB_EVENT_NAME": event_name, "GITHUB_EVENT_PATH": event_path,
               "GITHUB_REPOSITORY": REPO, "GITHUB_TOKEN": "t", "GITHUB_API_URL": f"http://127.0.0.1:{fake.port}",
               "GITHUB_STEP_SUMMARY": summary, "BLOCKED_PATTERNS": patterns}
        p = subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True, text=True, timeout=60)
        text = p.stdout + p.stderr + (read(summary) if os.path.exists(summary) else "")
        return p.returncode, text, fake

    def assert_no_detail(self, text, *values):
        """The output never carries the matched text, a line, which pattern or how many."""
        for v in values or (BLOCKED_NAME,):
            self.assertNotIn(v, text)
        self.assertNotRegex(text, r"(?i)\bline \d|pattern #\d|entry #\d|(?<!#)\b\d+ (match|hit)")

    def assert_labelled(self, fake, n):
        self.assertEqual(fake.posts, [(f"/repos/{REPO}/issues/{n}/labels", {"labels": ["private-value"]})])

    def test_issues_event_body_hit_labels_and_fails(self):
        rc, text, fake = self.run_scan("issues", {"issue": {"number": 12}},
                                       routes_for(issue(12, body=f"see {BLOCKED_NAME}/tools\nsecond line")))
        self.assertEqual(rc, 1)
        self.assertIn("- issue #12 body", text)
        self.assertNotIn("issue #12 title", text)
        self.assert_labelled(fake, 12)
        self.assert_no_detail(text)

    def test_issue_comment_event_japanese_comment_hit(self):
        comments = [{"id": 1001, "body": "問題なし", "user": HUMAN},
                    {"id": 1002, "body": f"社内の {BLOCKED_NAME} 環境で再現しました", "user": HUMAN}]
        rc, text, fake = self.run_scan("issue_comment", {"issue": {"number": 12}},
                                       routes_for(issue(12), comments))
        self.assertEqual(rc, 1)
        self.assertIn("- comment 1002 on #12", text)
        self.assertNotIn("comment 1001", text)
        self.assert_labelled(fake, 12)
        self.assert_no_detail(text)

    def test_pull_request_target_title_hit(self):
        rc, text, fake = self.run_scan("pull_request_target", {"pull_request": {"number": 7}},
                                       routes_for(issue(7, title=f"Port from {BLOCKED_NAME}", pr=True)))
        self.assertEqual(rc, 1)
        self.assertIn("- pull request #7 title", text)
        self.assert_labelled(fake, 7)
        self.assert_no_detail(text)

    def test_pull_request_review_body_hit(self):
        ev = {"pull_request": {"number": 7, "head": {"repo": {"full_name": REPO}}}, "repository": {"full_name": REPO}}
        rc, text, fake = self.run_scan("pull_request_review", ev, routes_for(
            issue(7, pr=True), reviews=[{"id": 501, "body": f"as in {BLOCKED_NAME}", "user": HUMAN}]))
        self.assertEqual(rc, 1)
        self.assertIn("- review 501 on #7", text)
        self.assert_labelled(fake, 7)
        self.assert_no_detail(text)

    def test_pull_request_review_comment_hit(self):
        ev = {"pull_request": {"number": 7, "head": {"repo": {"full_name": REPO}}}, "repository": {"full_name": REPO}}
        rc, text, fake = self.run_scan("pull_request_review_comment", ev, routes_for(
            issue(7, pr=True), review_comments=[{"id": 601, "body": f"copied from {BLOCKED_NAME}", "user": HUMAN}]))
        self.assertEqual(rc, 1)
        self.assertIn("- review comment 601 on #7", text)
        self.assert_labelled(fake, 7)
        self.assert_no_detail(text)

    def test_bot_text_labels_and_passes_with_warning(self):
        rc, text, fake = self.run_scan("issue_comment", {"issue": {"number": 12}}, routes_for(
            issue(12), [{"id": 1003, "body": f"Found a reference to {BLOCKED_NAME}", "user": BOT}]))
        self.assertEqual(rc, 0)
        self.assertIn("::warning::", text)
        self.assertNotIn("::error::", text)
        self.assertIn("- comment 1003 on #12 (written by a bot)", text)
        self.assert_labelled(fake, 12)
        self.assert_no_detail(text)

    def test_bot_hit_fails_when_the_label_cannot_be_written(self):
        rc, text, fake = self.run_scan("issue_comment", {"issue": {"number": 12}}, routes_for(
            issue(12), [{"id": 1004, "body": f"Found a reference to {BLOCKED_NAME}", "user": BOT}]), read_only=True)
        self.assertEqual(rc, 1)
        self.assertIn("label could not be added", text)
        self.assert_no_detail(text)

    def test_clean_text_keeps_the_label(self):
        rc, text, fake = self.run_scan("issues", {"issue": {"number": 12}},
                                       routes_for(issue(12, labels=["private-value", "bug"])))
        self.assertEqual(rc, 0)
        self.assertEqual(fake.posts, [])   # the fake has no DELETE either: a removal attempt would crash the run
        self.assertIn("#12: current text clean; delete the old revision from the edit history", text)
        self.assertIn("remove the `private-value` label", text)

    def test_fork_review_event_without_secret_runs_builtins_and_passes(self):
        ev = {"pull_request": {"number": 7, "head": {"repo": {"full_name": "outsider/widgets"}}},
              "repository": {"full_name": REPO}}
        rc, text, fake = self.run_scan("pull_request_review", ev, routes_for(
            issue(7, pr=True), reviews=[{"id": 502, "body": f"fails in {HOME_PATH} and {BLOCKED_NAME}", "user": HUMAN}]),
            patterns="", read_only=True)
        self.assertEqual(rc, 0)
        self.assertIn("BLOCKED_PATTERNS unavailable (review event from a fork): built-ins only", text)
        self.assertIn("- review 502 on #7", text)                      # the built-in still caught it
        self.assertIn("label could not be added (POST /repos/acme/widgets/issues/7/labels returned 403)", text)
        self.assert_no_detail(text, HOME_PATH, BLOCKED_NAME)

    def test_sweep_scans_recent_threads_with_all_patterns(self):
        # The review a fork event could only check with the built-ins: the sweep has the secret and a write token
        routes = routes_for(issue(7, pr=True), reviews=[{"id": 503, "body": f"same as {BLOCKED_NAME}", "user": HUMAN}])
        routes.update(routes_for(issue(8)))
        routes.update({"/issues": [issue(8)], "/issues/comments": [],
                       "/pulls/comments": [{"id": 9, "pull_request_url": f"https://api.github.com/repos/{REPO}/pulls/7"}]})
        rc, text, fake = self.run_scan("schedule", {"schedule": "17 3 * * *"}, routes)
        self.assertEqual(rc, 1)
        self.assertIn("- review 503 on #7", text)
        self.assertNotIn("#8", text)
        self.assert_labelled(fake, 7)
        self.assertTrue(any(g.startswith(f"/repos/{REPO}/issues?state=all&since=") for g in fake.gets))
        self.assert_no_detail(text)

    def test_sweep_all_input_scans_every_thread(self):
        routes = routes_for(issue(3, body=f"old {BLOCKED_NAME} note"))
        routes["/issues"] = [issue(3)]
        rc, text, fake = self.run_scan("workflow_dispatch", {"inputs": {"all": "true"}}, routes)
        self.assertEqual(rc, 1)
        self.assertIn("- issue #3 body", text)
        self.assertFalse(any("since=" in g for g in fake.gets))

    def test_empty_secret_runs_builtins_and_says_so(self):
        rc, text, fake = self.run_scan("issues", {"issue": {"number": 12}},
                                       routes_for(issue(12, body=f"logs are in {HOME_PATH}")), patterns="")
        self.assertEqual(rc, 1)
        self.assertIn("BLOCKED_PATTERNS not set, built-ins only.", text)
        self.assertIn("- issue #12 body", text)
        self.assert_no_detail(text, HOME_PATH)

    def test_invalid_pattern_fails_with_the_index_only(self):
        rc, text, fake = self.run_scan("issues", {"issue": {"number": 12}}, routes_for(issue(12)),
                                       patterns="acme-ok\n\nacme-(")
        self.assertEqual(rc, 1)
        self.assertIn("BLOCKED_PATTERNS entry #2 is not a valid regex", text)
        self.assertNotIn("acme-(", text)
        self.assertEqual(fake.gets, [])

    def test_comment_on_a_later_page_is_scanned(self):
        comments = [{"id": 2001, "body": "fine", "user": HUMAN}, {"id": 2002, "body": "fine too", "user": HUMAN},
                    {"id": 2003, "body": f"moved from {BLOCKED_NAME}", "user": HUMAN}]
        rc, text, fake = self.run_scan("issues", {"issue": {"number": 12}}, routes_for(issue(12), comments),
                                       paged=["/issues/12/comments"])
        self.assertEqual(rc, 1)
        self.assertIn("- comment 2003 on #12", text)

    def test_api_failure_fails_the_job_without_a_body(self):
        rc, text, fake = self.run_scan("issues", {"issue": {"number": 404}}, {})
        self.assertEqual(rc, 1)
        self.assertIn("GET /repos/acme/widgets/issues/404 returned 404; the scan did not finish", text)
        self.assertNotIn("Not Found", text)


class LeakPatternsTest(unittest.TestCase):
    def test_blocked_patterns_parsing(self):
        got = leak_patterns.blocked("acme-internal\n\n   \n(?i)ACME-[a-z]+-private\n")
        self.assertEqual([rx.pattern for rx in got], ["acme-internal", "(?i)ACME-[a-z]+-private"])
        self.assertTrue(got[1].search("see acme-web-private"))
        self.assertFalse(got[0].search("see ACME-INTERNAL"))   # case-insensitivity is opt-in, per pattern

    def test_leaks_puts_builtins_before_blocked(self):
        self.assertEqual([what for _, what in leak_patterns.leaks("acme-internal")],
                         ["absolute home directory path", "email address", "BLOCKED_PATTERNS"])


class WorkflowTest(unittest.TestCase):
    def test_event_fields_never_reach_a_run_block(self):
        lines = read(WORKFLOW).splitlines()
        uses = [ln.strip() for ln in lines if "github.event" in ln and not ln.lstrip().startswith("#")]
        self.assertTrue(uses)
        for ln in uses:
            self.assertRegex(ln, r"^(ref|group): ")   # an action input and the concurrency group, never a script

    def test_checkout_is_the_default_branch_without_credentials(self):
        text = read(WORKFLOW)
        self.assertEqual(text.count("uses: actions/checkout@"), 1)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("head.sha", text)
        self.assertNotIn("head.ref", text)


if __name__ == "__main__":
    unittest.main()
