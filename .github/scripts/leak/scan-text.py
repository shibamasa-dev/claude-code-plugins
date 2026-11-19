#!/usr/bin/env python3
"""Scan issue / PR text (title, body, comments, reviews, review comments) for private values.

Run by .github/workflows/text-scan.yml. The patterns are the ones check-repo.py uses on file contents
(leak_patterns.py: the built-ins plus the BLOCKED_PATTERNS secret).

- An event for item N re-scans the whole thread of N through the API, so setting the label follows one
  rule whichever comment triggered the run. `schedule` / `workflow_dispatch` sweep the threads updated in
  the last 26 hours (workflow_dispatch input `all`: every thread)
- A hit adds the label `private-value` and fails the job. Text written by a bot gets the label and a
  warning, and the job passes (someone else has to fix it). The label is never removed here: the old
  text stays readable in the edit history until someone deletes that revision
- The output names the item and the field only ("comment 1234567 on #12"). Never the matched text, a
  line, which pattern or how many: the log is public, and more detail would let an outside author
  probe for the blocked names
- The event is read from $GITHUB_EVENT_PATH and nothing in it is executed

Local use (reads only, nothing is written with --dry-run):
  GITHUB_REPOSITORY=owner/repo GITHUB_TOKEN=$(gh auth token) python3 scan-text.py --issue 12 --dry-run
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leak_patterns  # noqa: E402

LABEL = "private-value"
API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
PR_EVENTS = ("pull_request_target", "pull_request_review", "pull_request_review_comment")
SWEEP_HOURS = 26  # a daily run plus slack for a late start
# Seconds one thread may take to match (the env var is for tests). The built-ins are linear in the text,
# but a BLOCKED_PATTERNS entry may not be, and one slow thread must not keep the sweep from the others
THREAD_BUDGET = float(os.environ.get("TEXT_SCAN_THREAD_BUDGET") or 60)


class ApiError(Exception):
    """A failed API call. Carries the method, the path and the status only, never a response body."""


class OverBudget(Exception):
    """Matching one thread took longer than THREAD_BUDGET."""


def api(method, url, body=None):
    """returns (parsed JSON, Link header). url is a path under the repo or an absolute API URL."""
    if not url.startswith(API + "/"):
        url = f"{API}/repos/{REPO}{url}"
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "text-scan"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    path = url[len(API):].split("?")[0]
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r), r.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        raise ApiError(f"{method} {path} returned {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ApiError(f"{method} {path} failed ({type(e).__name__})") from None


def pages(path):
    """Every element of a paginated list (follows the Link header's rel="next")."""
    url = f"{path}{'&' if '?' in path else '?'}per_page=100"
    while url:
        data, link = api("GET", url)
        yield from data
        url = None
        for part in link.split(","):
            target, _, rel = part.partition(";")
            if 'rel="next"' in rel:
                url = target.strip().strip("<>")


def is_bot(user):
    return (user or {}).get("type") == "Bot"


def thread(n):
    """returns (has the label, [(field name, text, written by a bot)]) for issue or PR n."""
    issue, _ = api("GET", f"/issues/{n}")
    is_pr = bool(issue.get("pull_request"))
    kind = "pull request" if is_pr else "issue"
    bot = is_bot(issue.get("user"))
    fields = [(f"{kind} #{n} title", issue.get("title"), bot), (f"{kind} #{n} body", issue.get("body"), bot)]
    for c in pages(f"/issues/{n}/comments"):
        fields.append((f"comment {c['id']} on #{n}", c.get("body"), is_bot(c.get("user"))))
    if is_pr:
        for r in pages(f"/pulls/{n}/reviews"):
            fields.append((f"review {r['id']} on #{n}", r.get("body"), is_bot(r.get("user"))))
        for c in pages(f"/pulls/{n}/comments"):
            fields.append((f"review comment {c['id']} on #{n}", c.get("body"), is_bot(c.get("user"))))
    labelled = any(lb.get("name") == LABEL for lb in issue.get("labels") or [])
    return labelled, fields


def matches(text, patterns, deadline):
    # Line by line, as check-repo.py reads files, so one pattern means the same thing in both scans
    for line in (text or "").splitlines():
        if time.monotonic() > deadline:
            raise OverBudget
        if any(rx.search(line) for rx, _ in patterns):
            return True
    return False


def sweep_numbers(everything):
    """Issue / PR numbers to sweep: all of them, or the ones touched in the last SWEEP_HOURS hours."""
    if everything:
        return sorted(i["number"] for i in pages("/issues?state=all"))
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(hours=SWEEP_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    numbers = {i["number"] for i in pages(f"/issues?state=all&since={since}")}
    # Comments are listed too, in case an edit to one does not move the thread's own updated_at
    for path, key in (("/issues/comments", "issue_url"), ("/pulls/comments", "pull_request_url")):
        for c in pages(f"{path}?since={since}"):
            tail = (c.get(key) or "").rsplit("/", 1)[-1]
            if tail.isdigit():
                numbers.add(int(tail))
    return sorted(numbers)


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    name = os.environ.get("GITHUB_EVENT_NAME", "")
    event = {}
    if os.environ.get("GITHUB_EVENT_PATH"):
        with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
            event = json.load(f)
    out = []      # job summary lines (also printed)
    failed = False

    try:
        patterns = leak_patterns.leaks(text=True)
    except leak_patterns.InvalidPattern as e:
        print(f"::error::{e}")
        return 1

    pr = event.get("pull_request") or {}
    from_fork = name in PR_EVENTS[1:] and \
        ((pr.get("head") or {}).get("repo") or {}).get("full_name") != (event.get("repository") or {}).get("full_name")
    if not os.environ.get("BLOCKED_PATTERNS", "").strip():
        if from_fork:
            out.append("BLOCKED_PATTERNS unavailable (review event from a fork): built-ins only."
                       " The daily sweep scans this thread with all patterns.")
        else:
            out.append("BLOCKED_PATTERNS not set, built-ins only.")

    try:
        if "--issue" in args:
            numbers = [int(args[args.index("--issue") + 1])]
        elif name in ("issues", "issue_comment"):
            numbers = [event["issue"]["number"]]
        elif name in PR_EVENTS:
            numbers = [pr["number"]]
        elif name in ("schedule", "workflow_dispatch"):
            everything = str((event.get("inputs") or {}).get("all", "")).lower() == "true"
            numbers = sweep_numbers(everything)
            out.append(f"Sweep: {'every thread' if everything else f'threads updated in the last {SWEEP_HOURS} hours'}.")
        else:
            print(f"::error::text-scan: event '{name}' is not handled")
            return 1

        for n in numbers:
            # One thread that errors or runs over its budget must not stop the threads after it (the sweep)
            try:
                labelled, fields = thread(n)
                deadline = time.monotonic() + THREAD_BUDGET
                human = [what for what, text, bot in fields if not bot and matches(text, patterns, deadline)]
                bots = [what for what, text, bot in fields if bot and matches(text, patterns, deadline)]
            except (ApiError, OverBudget) as e:
                why = str(e) if isinstance(e, ApiError) else f"matching took longer than {THREAD_BUDGET:g} s"
                out.append(f"#{n}: the scan did not finish ({why}).")
                print(f"::error::text-scan: the scan of #{n} did not finish")
                failed = True
                continue
            if not human and not bots:
                if labelled:
                    out.append(f"#{n}: current text clean; delete the old revision from the edit history,"
                               f" then remove the `{LABEL}` label.")
                continue
            out.append(f"#{n}: text matches a private-value pattern. Edit it, delete the old revision from the"
                       f" edit history, then remove the `{LABEL}` label:")
            out += [f"- {what}" for what in human] + [f"- {what} (written by a bot)" for what in bots]
            if not labelled and not dry_run:
                try:
                    api("POST", f"/issues/{n}/labels", {"labels": [LABEL]})
                except ApiError as e:
                    out.append(f"#{n}: the `{LABEL}` label could not be added ({e}).")
                    if not from_fork:
                        # Only a review event from a fork is expected to fail here (read-only token; the sweep
                        # adds the label). Anywhere else a missing label must not look like a finished scan
                        failed = True
                        print(f"::error::text-scan: the `{LABEL}` label could not be added to #{n}")
            if human and not from_fork:
                failed = True
                print(f"::error::text-scan: text on #{n} matches a private-value pattern (see the job summary)")
            else:
                print(f"::warning::text-scan: text on #{n} matches a private-value pattern (see the job summary)")
    except ApiError as e:
        print(f"::error::text-scan: {e}; the scan did not finish")
        failed = True
    except (KeyError, TypeError, ValueError, IndexError) as e:
        # The type only: a message could quote the text being scanned
        print(f"::error::text-scan: unexpected data ({type(e).__name__}); the scan did not finish")
        failed = True

    if not any(line.startswith("#") for line in out):
        out.append("No private values found in the current text.")
    text = "\n".join(["### text-scan", ""] + out) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
