#!/bin/sh
# Runs every motion-video eval. It launches Chrome, so run it outside Claude Code's Bash sandbox.
#   sh <motion-video skill directory>/evals/run.sh [--only <name>] [--work <dir>]
# Outputs go to --work (default under os.tmpdir()). Exit code 0 = every assertion PASSed.
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
exec node "$DIR/run_evals.mjs" "$@"
