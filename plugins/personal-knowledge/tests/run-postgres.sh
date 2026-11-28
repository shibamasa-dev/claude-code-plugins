#!/bin/bash
# Run relationship-ledger's tests against Postgres: a throwaway postgres:16 container, and the server under uv
# (which adds psycopg). Needs docker, psql and uv. The other test-*.sh of this plugin don't touch a database and
# run again here unchanged.
#
# Usage: bash tests/run-postgres.sh
set -u
cd "$(dirname "$0")" || exit 1
port=${LEDGER_PG_PORT:-55436}
cid=$(docker run --rm -d -e POSTGRES_HOST_AUTH_METHOD=trust -p "127.0.0.1:$port:5432" postgres:16) || exit 1
trap 'docker stop "$cid" >/dev/null' EXIT
export LEDGER_PG_ADMIN_URL="postgresql://postgres@127.0.0.1:$port/postgres"
for _ in $(seq 60); do psql "$LEDGER_PG_ADMIN_URL" -X -q -c 'SELECT 1' >/dev/null 2>&1 && break; sleep 1; done
export LEDGER_SERVER_CMD="uv run --quiet --script"
bash run-all.sh pg-file-only.sh
