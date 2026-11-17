# Skill CLI Design

Use this reference when a skill may include scripts, a CLI, a mini app, a daemon, service registration, or operational logs.

## Basic Principle

Skill CLIs should be safe for both humans and agents. Commands should be predictable, dry-run friendly, inspectable, and clear about config, state, logs, and side effects.

## Command Structure

Do not force every main operation through `run`.

Use `run` only when the skill has one obvious primary operation. If the skill has multiple primary operations, expose domain verbs as subcommands.

Common management commands:

- `doctor`
- `init`
- `status`
- `logs`
- `stop`
- `config`
- `reset`
- `export`

Example domain commands:

- `index`
- `search`
- `sync`
- `capture`
- `render`
- `generate`
- `evaluate`
- `migrate`
- `serve`
- `daemon`

Avoid:

- putting every operation behind `run`
- hiding real subcommands behind `run --mode`
- making logs or status unable to show which operation ran

## Required Operational Commands

### `doctor`

Check the execution environment.

Useful checks:

- dependencies
- build status
- config presence
- database path and schema state
- network or credentials when needed
- write permissions for state, logs, cache, and outputs

Provide `doctor --json` when practical.

### `init`

Initialize local state, config, database schema, or service registration.

For daemon/service CLIs, include service registration paths:

```bash
<cli> init --local
<cli> init --systemd
<cli> init --launchd
<cli> init --print-service-file
<cli> init --dry-run
```

Rules:

- Default behavior should avoid destructive changes.
- System registration and remote DB setup require explicit user approval.
- `--dry-run` should show files, services, database schema, and environment variables that would be created or changed.
- Provide `--print-service-file` even if direct service installation is supported.

### `status`

Show current state:

- last operation
- daemon running state
- local DB path or remote DB target
- queue or pending work
- config source
- version
- log path and current log size

Provide `status --json` when practical.

### `logs`

Show logs without making users know internal paths.

Useful forms:

```bash
<cli> logs
<cli> logs --follow
<cli> logs --since 1h
<cli> logs --json
```

### `stop`

Stop the daemon or service. If a system service is registered, stop that unit rather than only killing a process.

### `reset`

Reset local state. Because this can be destructive, require confirmation or `--yes`.

### `export`

Export state or memory in a portable form:

```bash
<cli> export --format json
<cli> export --format sqlite
```

## Daemons

Daemon-capable CLIs should support foreground execution for debugging:

```bash
<cli> daemon
<cli> daemon --foreground
```

Document:

- start method
- stop method
- service registration method
- log location
- config location
- state/database location
- upgrade method
- uninstall method
- crash behavior

## Logs

CLI or daemon skills must prevent unbounded log growth.

Required:

- log rotation or a size cap
- retention period or maximum file count
- debug/verbose logging as explicit opt-in
- no secrets or private memory in logs
- `logs` or `status` shows log path and current size

Recommended:

- default log level is `info` or quieter
- support `--log-level debug`
- document stdout/stderr vs file logging behavior
- if systemd, launchd, or a supervisor owns retention, document that assumption and the expected retention settings

## Config

Document config precedence:

1. CLI flags
2. environment variables
3. config file
4. defaults

Do not store secrets in plaintext config unless the user explicitly accepts that tradeoff. Prefer environment variables or an existing secret manager.

## Machine-Readable Output

Provide JSON output for agent/script use:

```bash
<cli> status --json
<cli> doctor --json
<cli> <domain-command> --json
```

Human output should be readable. JSON output should be stable enough for scripts.

## Build And Distribution

If the CLI needs a build step, keep the build system in the skill directory (state-like output goes under `${CLAUDE_PLUGIN_DATA}`).

Document:

- install
- build
- test
- smoke test
- clean

Example:

```bash
npm install
npm run build
npm test
<cli> doctor
<cli> <domain-command> --dry-run
```
