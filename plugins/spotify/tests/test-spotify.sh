#!/bin/bash
# Runs spotify.py offline against a local mock Spotify and a recording op stub (see spotify_cases.py) and prints one
# verdict row per case in cases.json. Exits with the runner's status, so a crashed runner is a mismatch in run-all.sh.
cd "$(dirname "$0")" || exit 1
python3 -I -B spotify_cases.py
exit $?
