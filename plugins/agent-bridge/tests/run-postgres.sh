#!/bin/bash
# The schema tests (pg-sql.sh) on a throwaway postgres:16 container. Needs docker and psql.
#
# Usage: bash tests/run-postgres.sh
# Prints the same rows and totals line as run-all.sh, and exits 1 on any mismatch.
set -u
cd "$(dirname "$0")" || exit 1
port=${AGENT_BRIDGE_PG_PORT:-55433}
cid=$(docker run --rm -d -e POSTGRES_HOST_AUTH_METHOD=trust -p "127.0.0.1:$port:5432" postgres:16) || exit 1
trap 'docker stop "$cid" >/dev/null' EXIT
export PGOPTIONS="-c client_min_messages=warning"
export AGENT_BRIDGE_PG_URL="postgresql://postgres@127.0.0.1:$port/postgres"
for _ in $(seq 60); do psql "$AGENT_BRIDGE_PG_URL" -X -q -c 'SELECT 1' >/dev/null 2>&1 && break; sleep 1; done
bash pg-sql.sh 2>&1 | awk '
  /\(expect / {
    got = ""; want = ""
    if (match($0, /-> *[^ ]+ \(expect/)) { got = substr($0, RSTART, RLENGTH); sub(/^-> */, "", got); sub(/ \(expect$/, "", got) }
    if (match($0, /\(expect [^)]+\)/)) { want = substr($0, RSTART + 8, RLENGTH - 9) }
    if (got == "" || want == "" || got != want) { bad++; print "❌" $0 } else { ok++; print "  " $0 }
    next }
  {print}
  END {printf "\n==== %d as expected / %d mismatches ====\n", ok, bad+0; exit (bad > 0 || ok == 0)}'
