# Notes on cloud execution environments (researched 2026-08-15, checked against the official docs)

Sources: https://code.claude.com/docs/en/cloud-environments.md /
https://code.claude.com/docs/en/hooks.md / https://code.claude.com/docs/en/env-vars.md /
https://claude.com/docs/cowork/overview.md

## Environment variables usable for detecting remote

| Variable | Status | Use |
|------|------|------|
| `CLAUDE_CODE_REMOTE` | **Official**. `"true"` only on Anthropic-managed remote infrastructure | **Primary check**. Never set locally |
| `CLAUDE_CODE_ENTRYPOINT` | Unofficial (not in the env reference; values may come and go) | Secondary check (`remote_*` prefix) + platform branching inside remote (`remote_cowork` / `remote_desktop`). Locally it takes several values such as `cli` / `claude-desktop` → **"not cli = remote" is wrong** |
| `CLAUDE_CODE_BRIDGE_SESSION_ID` | Official | Set on **local sessions under Remote Control** (note: not remote. Remote Control runs on your own machine) |
| `CLAUDE_CODE_REMOTE_SESSION_ID` | Official | Cloud session ID (`cse_` form) |
| `CLAUDE_ENV_FILE` | Official | Appending `export FOO=bar` here persists an environment variable for the whole session |
| `CLAUDE_PROJECT_DIR` | Official | Repository root. Usable inside a hook's command |

- Cowork also has a local execution mode. With `CLAUDE_CODE_REMOTE` as the primary check, "Cowork but local" does not misfire.
- This skill's gate additionally allows the explicit override `REMOTE_SETUP_FORCE=1`
  (for Codex / Cursor adapters and testing. Do not loosen or remove the gate otherwise).

## The official two-layer setup mechanism (claude.ai/code)

| Layer | Defined in | Runs | Privileges |
|----|---------|------|------|
| Setup script (environment layer) | claude.ai/code environment dialog | At new session start, before Claude Code starts, only when there is no cache | **root** |
| SessionStart hook (session layer) | the repo's `.claude/settings.json` | Every session (matcher: `startup|resume`, etc.) | normal user |

**Division of roles (documented officially)**: the Setup script is for "provisioning the VM itself"
(toolchains and CLIs not preinstalled). The repository's project setup
(`npm install` etc.) goes in the SessionStart hook.

### Setup script constraints (official)

- **Write it self-contained**: assume the repository does not exist yet (a one-liner that references a script in the repo does not work).
  Install into repo-independent fixed paths (apt / global CLIs / system pip)
- **Within about 5 minutes** (otherwise the environment cache cannot be built. Parallelize independent installs with `&` + `wait`)
- **exit 0 is mandatory** (non-zero makes the session fail to start. Add `|| true` to non-essential steps)
- Network follows the environment's setting (the default, Trusted, allows the major registries)

### Environment cache (official)

- After the Setup script finishes, the filesystem is **snapshotted** and later sessions start from it
  (the Setup script is skipped). **The cache is per environment and repo-independent**
- **Only files** survive (started processes, DBs and docker compose stacks do not → start them in the hook every session)
- Rebuilt when the Setup script or network permissions change, or after the roughly **7-day** expiry. Resuming a session does not re-run it

### SessionStart hook behavior

- Cloud sessions read **only the repo's settings.json and org managed settings**
  (user-level `~/.claude/settings.json` is not read)
- stdout is injected into the agent's context → keep output to 1–3 lines
- If stdout starts with `{` it is parsed as JSON (`{"async": true, "asyncTimeout": 300000}` makes it async.
  Build it synchronous first, and consider async if it is slow)
- The hook timeout defaults to 60 seconds (this skill sets `timeout: 120` in the hook definition)
- Design it not to stop the session on failure (always exit 0 + print a WARNING)

## VM specs and constraints (Anthropic-hosted)

- Ubuntu 24.04 LTS (x86_64) / about 4 vCPU / 16GB RAM / 30GB disk. The VM stops the task when resources are exceeded
- Preinstalled: Python 3 (pip, poetry, uv, pytest, ruff...) / Node 20-22 (npm, yarn, pnpm...) /
  Ruby / PHP / Java / Go / Rust / Docker / PostgreSQL 16 / Redis 7 / git, jq, yq, ripgrep, tmux
- **System pip is PEP 668 (externally-managed)** → in the root Setup script use
  `pip install --break-system-packages`. From the session layer's venv,
  `python3 -m venv --system-site-packages` makes the system packages visible
- No GUI → viewers (ocp-vscode etc.) do not work. CAD is verified headless (export + numeric checks)
- devcontainers are not supported in cloud sessions
- Network: None / **Trusted (default: npm, PyPI, RubyGems, crates.io, etc. + GitHub)** / Custom / Full.
  GitHub access goes through a proxy; fetching release assets of repos not tied to the session returns 403
- Environment variables and the Setup script are visible to everyone using the environment = **do not put secrets there** (no dedicated secrets store yet)

## Adapters for other platforms (future)

Both have cloud-only setup mechanisms, so a thin adapter that calls the session-layer core (setup.sh)
with `REMOTE_SETUP_FORCE=1` is enough. Fold the environment-layer content into each mechanism.

### OpenAI Codex (cloud)

- The environment's `setup` script runs before the agent starts (container state is cached for about 12 hours)
- Adapter: merge the content of environment-setup.sh into the setup script and append
  `REMOTE_SETUP_FORCE=1 bash scripts/remote-setup/setup.sh` at the end
- Persist environment variables in `~/.bashrc`; pass lint/test commands via `AGENTS.md`
- Docs: https://developers.openai.com/codex/cloud/environments

### Cursor (Cloud Agents)

- `install` (must be idempotent) / `start` / `terminals` in `.cursor/environment.json`, committed to the repo
- Adapter: start from `"install": "REMOTE_SETUP_FORCE=1 bash scripts/remote-setup/setup.sh"` and
  fold the environment layer into install too (it is cached). Secrets go in Cursor's own mechanism
- Docs: https://cursor.com/docs/cloud-agent/setup

## Not yet measured (as of 2026-08-15)

- Whether the SessionStart hook runs in cloud Cowork, and the actual value of `CLAUDE_CODE_REMOTE`, are to be measured in the first repo it is applied to
  (in a remote session, look for the `[remote-setup]` line and `~/.cache/remote-setup/*.log`)
