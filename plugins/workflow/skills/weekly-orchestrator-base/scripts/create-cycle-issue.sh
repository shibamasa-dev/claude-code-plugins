#!/bin/bash
# Creates this cycle's issue when no issue (open or closed) has exactly its title. The weekly-issue workflow runs it
# from the project repo's root, as a safety net for a cycle the orchestrator has not opened yet.
#
# The title, week and body come from cycle.py, the same script the orchestrator skill uses, so the two cannot drift.
# This file does no date arithmetic of its own. Issue Fields from the config's issue_fields are set best effort: a
# token without access to them leaves the issue created and prints a warning.
#
# Environment: GH_TOKEN (for gh), CYCLE_NOW (optional ISO instant, for tests), CYCLE_CONFIG (optional config path)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/cycle.XXXX")"
trap 'rm -rf "$T"' EXIT
cy() { python3 "$HERE/cycle.py" ${CYCLE_CONFIG:+--config "$CYCLE_CONFIG"} "$@"; }
get() { python3 -c 'import json,sys; v=json.load(open(sys.argv[1]))[sys.argv[2]]; print(v if isinstance(v,str) else json.dumps(v))' "$@"; }

cy new ${CYCLE_NOW:+--now "$CYCLE_NOW"} > "$T/new.json"
cy resolve ${CYCLE_NOW:+--now "$CYCLE_NOW"} > "$T/resolve.json"
title="$(get "$T/new.json" title)"
repo="$(get "$T/resolve.json" repo)"
echo "Cycle issue: $title ($repo)"

# Exact title over the issue list (open and closed), not the search API: its index lags behind a fresh issue
if cy exists --title "$title" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin)["exists"] else 1)'; then
  echo "An issue titled \"$title\" already exists; not creating another."
  exit 0
fi

get "$T/new.json" body > "$T/body.md"
url="$(gh issue create -R "$repo" --title "$title" --body-file "$T/body.md")"
echo "Created: $url"

get "$T/new.json" issue_fields > "$T/fields.json"
if [ "$(cat "$T/fields.json")" = "[]" ]; then
  exit 0
fi
number="${url##*/}"
id="$(gh issue view "$number" -R "$repo" --json id | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
python3 - "$T/fields.json" > "$T/query.graphql" <<'PY'
import json, sys
fields = json.load(open(sys.argv[1]))
items = ", ".join("{ " + ", ".join(f"{k}: {json.dumps(v)}" for k, v in f.items()) + " }" for f in fields)
print("mutation($issueId: ID!) { setIssueFieldValue(input: { issueId: $issueId, issueFields: [" + items + "] }) { clientMutationId } }")
PY
if ! gh api graphql -f issueId="$id" -f query="$(cat "$T/query.graphql")" > /dev/null; then
  echo "::warning::Issue Fields were not set on $url (the token may lack access); the issue itself was created."
fi
