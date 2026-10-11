---
name: remote-setup
description: >-
  Generates or updates a setup scaffold in a repository for remote execution environments
  (claude.ai/code cloud environments and Cowork cloud VMs). The output is gated so it never fires locally.
  Always use this skill when the user says "add/update remote setup", "make this repo usable in the
  cloud environment", "I want to run this repo on Cowork / claude.ai/code", "install dependencies when
  a remote session starts", "I want to use heavy tools such as CAD in the cloud", "remote setup",
  "create a session-start hook", or in Japanese 「リモートセットアップを追加/更新して」
  「クラウド環境でこのリポを使えるように」「Cowork / claude.ai/code でこのリポを動かしたい」
  「リモートセッション開始時に依存を入れたい」「CAD など重いツールをクラウドで使いたい」
  「session-start hook を作って」. It splits the tools a repo needs remotely into the environment layer
  (environment-setup.sh) and the session layer (steps.sh) and wires them up. Also use it to add or update
  tools in an existing scaffold, and for questions about supporting Codex / Cursor cloud agents.
last_reviewed: 2026-09-06
review_after: 2027-03-05
---

# remote-setup — generate a setup scaffold for remote execution environments

## Design principles

- Targets: claude.ai/code cloud environments and Cowork cloud VMs. Codex / Cursor cloud sandboxes
  are supported through a thin adapter that uses `REMOTE_SETUP_FORCE=1`.
- **Never fires locally.** The generated setup.sh runs past its opening gate only when
  `CLAUDE_CODE_REMOTE=true` (official flag, primary check), `CLAUDE_CODE_ENTRYPOINT=remote_*`
  (observed value, secondary check) or `REMOTE_SETUP_FORCE=1` (explicit override).
  "Anything other than `cli` is remote" is wrong (the local Desktop app is `claude-desktop`).
  Never remove or loosen this gate, for any reason.
- Match the official two-layer mechanism exactly (the role of each layer is documented officially):

| Layer | File | Runs | What goes there |
|----|---------|------|---------|
| **Environment layer** | `environment-setup.sh` → **paste its whole content** into the Setup script field on claude.ai | First time only, as root, snapshot cached for about 7 days | VM provisioning: apt, heavy packages, global CLIs. **Assume the repo does not exist yet: self-contained, fixed paths** |
| **Session layer** | `steps.sh` (driven by setup.sh) → SessionStart hook | Every session, as a normal user | Light work that follows the repo's state: dependency sync, venv, verify |

- Cloud sessions read **only the repo's `.claude/settings.json`** (user-level settings are not read).
  So the output must always be committed to the repo.
- **Always read** `references/cloud-environments.md` before generating, for the details
  (environment variables, VM specs, caching, adapters, sources).

## Steps

### 1. Generate the scaffold

```bash
python3 <path to this skill>/scripts/scaffold.py <repo-root>
```

| Path | Handling |
|------|------|
| `scripts/remote-setup/setup.sh` | Shared session-layer runner. **Overwritten from the template every time** (do not edit by hand) |
| `scripts/remote-setup/steps.sh` | Repo-specific session-layer steps. **Kept if it exists** |
| `scripts/remote-setup/environment-setup.sh` | Environment layer (the content pasted into the UI). **Kept if it exists** |
| `.claude/settings.json` | SessionStart hook merged in (existing settings kept, no duplicate added) |

### 2. Split the work across the two layers

Analyze the repo (package manifests, lockfiles, CLAUDE.md, CI config, main imports) and
assign the tools it needs. Criteria:

| Where | Criterion | Examples |
|--------|------|-----|
| `environment-setup.sh` (environment layer) | Needs root / over 30 seconds / does not change | apt, heavy CAD packages, global CLIs |
| `light_steps` (session layer) | Should follow the repo's state (idempotent, within a few tens of seconds) | `npm ci`, `pip install -e .`, creating a venv |
| `verify` (session layer) | Tells within seconds whether the environment is alive | `command -v`, import checks |

When unsure, use the session layer (running every time does no harm if it is idempotent). The environment layer has a limit of about 5 minutes.

Rules when implementing:
- **The environment layer is self-contained**: no references to the repo (it does not exist yet at that point). For system pip, use
  `pip install --break-system-packages` (Ubuntu 24.04 follows PEP 668).
- **Python uses `.venv` at the repo root in the session layer.** Heavy packages installed into the system by the environment layer
  are made visible with `python3 -m venv --system-site-packages`.
- **Non-interactive**: `-y` / `DEBIAN_FRONTEND=noninteractive`. In the environment layer, every step gets `|| true` (exit 0 is mandatory).
- List required environment variables in `REQUIRED_ENV_VARS`. **Never write their values in the repo** (they are set in the claude.ai
  environment dialog; setup only checks they exist and warns). Never commit secrets.
- List network hosts the default Trusted level does not cover in the comment at the top of steps.sh.

### 3. Local safety check (mandatory)

```bash
env -u CLAUDE_CODE_REMOTE -u REMOTE_SETUP_FORCE bash scripts/remote-setup/setup.sh; echo "exit=$?"
```

**It must print nothing and exit 0.** Any output means the gate is broken.
Also check the syntax of both scripts with `bash -n`.
⚠️ Never run it locally with `REMOTE_SETUP_FORCE=1` or `CLAUDE_CODE_REMOTE=true`
(real installs would run on the local machine). Limit logic checks to running verify on its own.

### 4. Report to the user (with this template)

Write the report in the user's language.

```
## remote-setup result
### Files generated or changed
- (list)
### Settings in the claude.ai/code environment dialog (done by the user)
1. Paste [the whole content] of scripts/remote-setup/environment-setup.sh into the Setup script field
   (committing alone does not run the environment layer. Re-paste after changing it = cache rebuild)
2. Environment variables: (the REQUIRED_ENV_VARS list, or "none")
3. Network access: (Trusted is enough / Custom + list of hosts)
### Verifying
Open a remote session and check that a [remote-setup] line appears in the context.
Detailed log: cat ~/.cache/remote-setup/<repo name>.log
* The hook takes effect in sessions started after it is merged into the default branch
```

## Update flow

- Session-layer changes only require editing steps.sh. When its hash changes, the hook in the next remote session
  automatically re-applies light_steps.
- For environment-layer changes, edit environment-setup.sh and ask the user to **re-paste it into the Setup script field on claude.ai**
  (re-pasting rebuilds the cache).
- To improve the shared part of setup.sh, update this skill first, then re-run scaffold.py in each repo to roll it out.

## Future support for Codex / Cursor

Keep the shared core (setup.sh) as it is, and add a thin adapter that calls
`REMOTE_SETUP_FORCE=1 bash scripts/remote-setup/setup.sh` from each platform's cloud-only setup mechanism.
See "Adapters for other platforms" in `references/cloud-environments.md` for the concrete steps.
