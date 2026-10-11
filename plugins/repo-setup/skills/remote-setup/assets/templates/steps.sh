#!/usr/bin/env bash
# Session-layer steps specific to this repository. Sourced by setup.sh (runs only remotely).
# Edit only this file and environment-setup.sh. setup.sh is the shared part (overwritten when the skill runs again).
#
# Do not put heavy installs (apt, heavy packages, global CLIs) here —
# they go in environment-setup.sh (the environment layer; its content is pasted into the Setup script on claude.ai).
#
# Network hosts required (outside the default Trusted allowlist): none
#   * If there are any, list them here and set Network access of the claude.ai environment to Custom and add them.

# Environment variables required for the session (WARNING if unset. Values are set in the claude.ai environment dialog)
REQUIRED_ENV_VARS=()

# Runs every session (via the SessionStart hook). Keep it idempotent and within a few tens of seconds.
# What goes here: light work that should follow the repository's state (dependency sync, creating a venv, etc.).
light_steps() {
  :
  # Example (Node): cd "$REPO_ROOT" && npm ci --no-audit --no-fund
  # Example (Python): expose heavy packages installed into the system by the environment layer via --system-site-packages
  #   [ -x "$REPO_ROOT/.venv/bin/python" ] || python3 -m venv --system-site-packages "$REPO_ROOT/.venv"
  #   "$REPO_ROOT/.venv/bin/pip" install -q -e "$REPO_ROOT"
}

# Light check that the environment is usable (exit 0 = OK). Runs every session, so keep it within a few seconds.
verify() {
  :
  # Example: "$REPO_ROOT"/.venv/bin/python -c "import build123d" 2>/dev/null
}
