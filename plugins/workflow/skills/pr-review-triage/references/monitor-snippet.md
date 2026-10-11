# Monitor snippet for waiting on PR reviews

The implementation of the `pr-review-triage` skill's heavy "wait" step when run locally (the cloud waits by subscribing to PR events, so it does not use this).
Start it with `persistent: true`; it runs until explicitly stopped with TaskStop. Put `api.github.com` in the Monitor's `allowed_domains`.

```bash
# ⚠️ This loop only picks up events after its start time. Before starting it, always sweep existing unresolved threads once
#    (the first review arrives a few minutes after the PR is created, so the Monitor alone misses it).
#    Unless non-bot posts (your own replies) are excluded, notifications flood and bury the real reviews.
# ⚠️ Monitor runs inside the sandbox, where gh fails TLS verification (x509: OSStatus -26276).
#    Don't use gh api; fetch with curl + gh auth token.
# ⚠️ Pass fetched results to jq with printf '%s'. The Bash tool is zsh, and zsh's echo expands \n inside JSON strings
#    into real newlines, which breaks jq (it only shows on stderr, and notifications come out as 0 items).
# Fetch and parse failures are reported as FETCH_FAILED / PARSE_FAILED (to tell them apart from "0 items").
TOKEN=$(gh auth token 2>/dev/null); [ -z "$TOKEN" ] && echo "FETCH_FAILED no_token"
API=https://api.github.com/repos/{owner}/{repo}
last=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# Authors of the bots to wait for (output of scripts/detect-bots.sh --regex; get it once before the Monitor and embed it)
BOTS='{bots_regex}'
# CodeRabbit's auto summary (walkthrough) is updated on every push, so its body is not notified.
# But with zero findings CodeRabbit creates no review and only writes completion inside this walkthrough,
# so "No actionable comments" and the not-reviewed signals (rate limited, plan limit) are emitted as status lines
# (without the former, completion can't be detected; the latter means "wait again", not "done").
# Not-reviewed signals can also come in a comment other than the summary, so they go to the status line even if $NOISE doesn't match.
NOISE='auto-generated comment: summarize|review in progress'
get() { curl -sf -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$1"; }
while true; do
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  for pr in {pr_numbers}; do
    # reviews doesn't support since (it is silently ignored and everything is returned), so filter in jq
    r=$(get "$API/pulls/$pr/reviews?per_page=100") || { echo "FETCH_FAILED PR#$pr reviews"; r='[]'; }
    printf '%s' "$r" | jq -r --arg l "$last" --arg b "$BOTS" --arg p "$pr" \
      '.[] | select(.submitted_at > $l) | select(.user.login | test($b; "i")) | "[PR#\($p) review] \(.user.login): \(.state) \(.body[0:200] | gsub("\n";" "))"' \
      || echo "PARSE_FAILED PR#$pr reviews"
    c=$(get "$API/pulls/$pr/comments?since=$last&per_page=100") || { echo "FETCH_FAILED PR#$pr comments"; c='[]'; }
    printf '%s' "$c" | jq -r --arg b "$BOTS" --arg p "$pr" \
      '.[] | select(.user.login | test($b; "i")) | "[PR#\($p) comment] \(.user.login) \(.path | split("/") | last):\(.line // .original_line) \(.body[0:250] | gsub("\n";" "))"' \
      || echo "PARSE_FAILED PR#$pr comments"
    i=$(get "$API/issues/$pr/comments?since=$last&per_page=100") || { echo "FETCH_FAILED PR#$pr issue_comments"; i='[]'; }
    printf '%s' "$i" | jq -r --arg b "$BOTS" --arg n "$NOISE" --arg p "$pr" \
      '.[] | select(.user.login | test($b; "i"))
        | if ((.body | test($n)) or (.body | test("rate limited|plan limit"; "i"))) then
            (if (.body | test("No actionable comments|rate limited|plan limit"; "i")) then "[PR#\($p) coderabbit-status] actionable_none=\(.body | test("No actionable comments")) not_reviewed_limit=\(.body | test("rate limited|plan limit"; "i"))" else empty end)
          else "[PR#\($p) issue-comment] \(.user.login): \(.body[0:250] | gsub("\n";" "))" end' \
      || echo "PARSE_FAILED PR#$pr issue_comments"
    # With zero findings, Codex and others don't appear in reviews and answer with a reaction (👍) on the PR. 👀 means reviewing
    x=$(get "$API/issues/$pr/reactions") || { echo "FETCH_FAILED PR#$pr reactions"; x='[]'; }
    printf '%s' "$x" | jq -r --arg l "$last" --arg b "$BOTS" --arg p "$pr" \
      '.[] | select(.created_at > $l) | select(.user.login | test($b; "i")) | "[PR#\($p) reaction] \(.user.login): \(.content)"' \
      || echo "PARSE_FAILED PR#$pr reactions"
  done
  last=$now
  sleep 30
done
```

## Wait only for CI (light PRs, and after a push that doesn't request a re-review)

Inside the Monitor, `gh` fails TLS verification in the sandbox (see the note in the snippet above), so fetch with curl instead of `gh pr checks --watch`. The command shows `pulls/<number>` and the repo URL, so dev-flow-gate counts it as "started waiting". CI comes in two kinds, check runs (GitHub Actions, etc.) and commit statuses (set by external CI), so watch both. When both are done, print one line and exit (`persistent` is not needed). If no check is attached to the head commit after 10 minutes, print `NO_CHECKS` and exit (CI is not counted as green). If fetching fails 5 times in a row (invalid token, missing permission, etc.), print `FETCH_GAVE_UP` and exit.

```bash
TOKEN=$(gh auth token 2>/dev/null); [ -z "$TOKEN" ] && { echo "FETCH_FAILED no_token"; exit 1; }
API=https://api.github.com/repos/{owner}/{repo}
get() { curl -sf -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$1"; }
seen=; since=$(date +%s); fails=0
while true; do
  sha=$(get "$API/pulls/{pr}" | jq -r '.head.sha // empty')
  runs=$([ -n "$sha" ] && get "$API/commits/$sha/check-runs?per_page=100")
  st=$([ -n "$sha" ] && get "$API/commits/$sha/status")
  if [ -z "$runs" ] || [ -z "$st" ]; then
    # With an invalid token or missing permission, retries never succeed. After 5 in a row (about 2.5 minutes), exit and report
    fails=$((fails + 1)); echo "FETCH_FAILED PR#{pr} checks ($fails/5)"
    [ "$fails" -ge 5 ] && { echo "[PR#{pr} ci] FETCH_GAVE_UP (fetching failed repeatedly; check gh auth status)"; break; }
    sleep 30; continue
  fi
  fails=0
  [ "$sha" != "$seen" ] && { seen=$sha; since=$(date +%s); }   # if a push changed the head, start counting again
  nrun=$(printf '%s' "$runs" | jq '.total_count')
  # A page holds up to 100. Anything not fetched (the gap to total_count) counts as not completed
  left=$(printf '%s' "$runs" | jq '.total_count as $t | (.check_runs | length) as $n | ([.check_runs[] | select(.status != "completed")] | length) + (if $t > $n then $t - $n else 0 end)')
  nst=$(printf '%s' "$st" | jq '.total_count')
  state=$(printf '%s' "$st" | jq -r '.state')   # also pending when there are none
  if [ $((nrun + nst)) = 0 ]; then
    # Right after a push there may still be 0, so don't exit immediately
    [ $(($(date +%s) - since)) -ge 600 ] && { echo "[PR#{pr} ci] NO_CHECKS (no check attached after 10 minutes)"; break; }
  elif [ "$left" = 0 ] && { [ "$nst" = 0 ] || [ "$state" != pending ]; }; then
    # If a push happened while waiting, don't exit on the old commit's results; recount on the next pass
    [ "$(get "$API/pulls/{pr}" | jq -r '.head.sha // empty')" != "$sha" ] && { sleep 30; continue; }
    { printf '%s' "$runs" | jq -r '.check_runs[] | "\(.name)=\(.conclusion)"'
      printf '%s' "$st" | jq -r '.statuses[] | "\(.context)=\(.state)"'; } | paste -sd' ' - | sed 's/^/[PR#{pr} ci] /'
    break
  fi
  sleep 30
done
```

Sweep before starting (list of unresolved threads; clear these first, then start the Monitor):

```bash
gh api graphql -f query='{ repository(owner:"{owner}", name:"{repo}") { pullRequest(number:{pr}) {
  reviewThreads(first:20) { nodes { isResolved comments(first:1) { nodes { author{login} path body } } } } } } }' \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
```

(The sweep runs outside the Monitor, so `gh` is fine. But Bash inside the sandbox hits the same TLS failure, so run it outside the sandbox.)

Note: Monitor notification bodies are truncated. After detecting something new, always **re-fetch the full text** of
reviews / comments with `gh api` before evaluating (don't judge from the notification body alone).

**Even if the timeout notification shows 0 items, don't read it as "nothing yet".** Re-check the primary source before deciding.
Also check the Monitor's output file (`tasks/<id>.output`) for leftover jq or curl errors.
