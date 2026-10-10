#!/bin/sh
# motion-video の eval を全部流す。Chrome を起動するので Claude Code の Bash sandbox 外で実行する。
#   sh <motion-video スキルのディレクトリ>/evals/run.sh [--only <name>] [--work <dir>]
# 生成物は --work（既定 os.tmpdir() 配下）に置く。終了コード 0 = 全 assertion PASS。
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
exec node "$DIR/run_evals.mjs" "$@"
