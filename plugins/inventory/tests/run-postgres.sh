#!/bin/bash
# Run the same tests against Postgres: a throwaway postgres:16 container, and the server under uv (for psycopg).
# Not part of CI (no Docker there). Needs docker, psql and uv.
#
# Usage: bash tests/run-postgres.sh
set -u
cd "$(dirname "$0")" || exit 1
port=${INVENTORY_PG_PORT:-55432}
cid=$(docker run --rm -d -e POSTGRES_HOST_AUTH_METHOD=trust -p "127.0.0.1:$port:5432" postgres:16) || exit 1
trap 'docker stop "$cid" >/dev/null' EXIT
export INVENTORY_PG_ADMIN_URL="postgresql://postgres@127.0.0.1:$port/postgres"
for _ in $(seq 60); do psql "$INVENTORY_PG_ADMIN_URL" -X -q -c 'SELECT 1' >/dev/null 2>&1 && break; sleep 1; done
export INVENTORY_SERVER_CMD="uv run --quiet --script"
INVENTORY_EXTRA_TESTS=pg-file-only.sh bash run-all.sh
