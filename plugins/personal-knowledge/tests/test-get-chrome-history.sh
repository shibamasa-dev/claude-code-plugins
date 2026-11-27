#!/bin/bash
# Runs get-chrome-history's script offline against fixture History databases built in a temp dir (see
# get_chrome_history_cases.py) and prints one verdict row per behaviour. Exits with the runner's status, so a crashed
# runner is a mismatch in run-all.sh.
cd "$(dirname "$0")" || exit 1
python3 -I get_chrome_history_cases.py
exit $?
