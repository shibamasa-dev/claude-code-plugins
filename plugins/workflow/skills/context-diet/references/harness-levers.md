# Injected-layer levers (specs confirmed by measurement)

Settings keys for trimming, **per project**, the "tool name list", "skills list", and "MCP server instructions" that are added to the system prompt every time. Based on reading the Claude Code 2.1.251 binary and verifying on a real machine on 2026-08-29.

> ⚠️ What is written here is **measured at that point in time**. Recheck after a version upgrade. Each section includes its verification commands.

## What can be set in which layer

| Layer | Allowlist | Denylist | Scope |
|---|---|---|---|
| User `~/.claude/settings.json` | — | **`deniedMcpServers`** | All projects on this machine |
| Project `.claude/settings.json` | — | **`deniedMcpServers`** / **`skillOverrides`** | Project |
| Projects entry in `~/.claude.json` | `enabledMcpServers` (**`computer-use` only**) | `disabledMcpServers` (everything else) | Project |
| `.claude/settings.local.json` | `enabledMcpjsonServers` `enableAllProjectMcpServers` | `disabledMcpjsonServers` | Only servers from `.mcp.json` |
| `managed-settings.json` (enterprise policy) | `allowedMcpServers` | `deniedMcpServers` `disableClaudeAiConnectors` | Whole machine |

The user can't choose allowlist vs. denylist. **The branch is decided by the server name**:

```js
var e0 = "computer-use";
function xve(e){ return e === e0 }
function _i(e){                                              // isDisabled(serverName)
  let t = li();                                              // project entry
  if (xve(e)) return !Nte(t.enabledMcpServers).includes(e);   // allowlist
  return Nte(t.disabledMcpServers).includes(e);               // denylist
}
```

```bash
BIN="$(readlink -f "$(command -v claude)")"   # the real file is versions/<ver>
strings -a "$BIN" | grep -c 'function _i(e){let t=li()'
strings -a "$BIN" | grep -o 'e0="computer-use"'
```

## `deniedMcpServers` (drop individual connectors)

The description says "Enterprise denylist", but **it works in both project and user settings.json** (measured).

**Put it in user `~/.claude/settings.json` and it applies to "all projects on this machine"** (measured on 2026-09-15 with Claude Code 2.1.272). The connector stays enabled on the claude.ai side, so you can **keep using it on other devices and the web while dropping it only on this PC**. Example use: on this PC you use the same service through a local MCP and don't want it duplicated by the claude.ai remote connector.

```json
"deniedMcpServers": [
  { "serverName": "claude.ai Notion" }
]
```

- Entries are **objects**, not strings. Besides `serverName`, `serverCommand` (array) / `serverUrl` are also used for matching
- The name must exactly match the display name in `claude mcp list` (claude.ai connectors are in the form `claude.ai <display name>`)
- A dropped server **disappears from the configuration**. It is not a disconnect (`claude mcp get "<name>"` returns "No MCP server named")
- Headless runs print **one line**: `Warning: claude.ai MCP servers blocked by enterprise policy: <name>, ...`. The wording is fixed and does not mean a misconfiguration. It does not appear in `claude mcp list`

⚠️ **It does not work on CLI-owned built-in servers.** Putting `claude-in-chrome` and `computer-use` in `deniedMcpServers` is ignored (they don't appear in the blocked warning either). The binary defines the reason codes side by side:

```js
Pf = "Builtin server is CLI-owned; ignored"                              // ← built-ins take this one first
Af = "Blocked by enterprise policy (allowedMcpServers/deniedMcpServers)"
```

To drop a built-in, use `/mcp disable <name>` (written to the projects entry in `~/.claude.json`; for `computer-use` only, it means removal from the `enabledMcpServers` allowlist). **Don't write it in settings.json** — an ineffective setting gets left in place because it looks like it works.

**Verify**:
```bash
claude mcp list                     # gone from the list
claude mcp get "claude.ai Notion"   # returns "No MCP server named"
claude -p 'reply OK' </dev/null 2>&1 | grep blocked   # the name appears in the blocked warning
```

## `skillOverrides` (drop from the skills list)

```json
"skillOverrides": {
  "gws-gmail": "user-invocable-only",
  "coderabbit:code-review": "off",
  "mysql": "name-only"
}
```

| Value | Behavior |
|---|---|
| `off` | Hidden from both the model and `/name` |
| `user-invocable-only` | **Hidden from the model, but can be started manually with `/name`** ← default for reduction |
| `name-only` | Keeps only the name and drops the description |
| Not set | Unchanged |

- The reduction equals the description's byte count

⚠️ **It works only on personal skills (`~/.claude/skills/*`). It does not work on plugin skills.**
We tried `frontend-design` / `mcp-apps:*` / `coderabbit:*` in both `plugin:skill` form (`"frontend-design:frontend-design"`) and bare form (`"frontend-design"`), in both `settings.json` and `settings.local.json`; none disappeared from the list. **skillOverrides has no way to drop plugin skills** (the only way is to disable the plugin itself via `enabledPlugins`). Assume it doesn't work on account-side skills (`small-business:*`, etc.) either.

**Verify** (headless sessions reread settings, so you can measure without restarting this session):
```bash
claude -p --model haiku 'Output ONLY JSON: {"<dropped skill>":<listed?>, "<kept skill>":<listed?>}' < /dev/null
```

⚠️ **The model hallucinates on this yes/no question.** Even if "dropped side false, kept side true" lines up, don't trust that alone. **Check the round trip** — remove the override, ask the same question, and confirm the side that was false returns to true. The final check is the Skills table in `/context` (ask the user to run it).

## Scope of plugin-provided MCP servers and skills

MCP servers (`plugin:<plugin>:<server>`) and skills that a plugin brings in take effect **in the scope where `enabledPlugins` is written**. The schema says:

> Enabled plugins using plugin-id@marketplace-id format. **Settings precedence is user < project < local < flag < policy**, so to disable a plugin that project settings enable, set it to false in `.claude/settings.local.json` — setting false in `~/.claude/settings.json` is overridden by the project.

So a plugin listed in `enabledPlugins` in `~/.claude/settings.json` is **enabled in every project**. For a plugin needed only in a specific repo:

- Remove it from user settings and write `{"<plugin>@<marketplace>": true}` in **that repo's project settings**. Move `extraKnownMarketplaces` along with it (the schema says "Typically used in repository `.claude/settings.json` to ensure team members have required plugin sources")
- ⚠️ **Writing `false` on the user side has no effect** (the project overrides it). Disable it in `.claude/settings.local.json`

**Choosing where to put it** — if the plugin is a lifeline for a resident session, **choose `.claude/settings.local.json` (not tracked by git)**. If it's in the tracked `settings.json`, the setting vanishes the moment the repo switches branches, and the resident session quietly loses the feature. Use `settings.json` when it must be shared, `settings.local.json` when it must survive branch switches.

⚠️ **Before moving it, check the cwd of the sessions that use the plugin.** Sessions started from launchd or external triggers may have an unexpected cwd, in which case project settings aren't read and the whole plugin drops out. Check both the plist's `WorkingDirectory` and the WORKDIR default in the startup script.

**Verify with a set of three** (measurable right after the move, without waiting for the resident session to restart):
```bash
cd <repo that should use it>      && claude mcp list | grep plugin:   # shows up
cd <repo that should not use it>  && claude mcp list | grep plugin:   # does not show up
cd <a third repo>                 && claude mcp list | grep plugin:   # not leaking
```

To drop a plugin MCP in just one project, writing `plugin:<plugin>:<server>` in `deniedMcpServers` has a smaller blast radius (unlike built-ins, this one works).

## Other

- **`disableClaudeAiConnectors`** (bool) — the schema says "When true in **any settings source** … **a project can opt out**, but a project-level false cannot override a user-level true". It can be used in project settings.json, but it **cuts all connectors**, so it's not an option for projects that use GitHub, etc.
- **`disabledMcpServers` in `~/.claude.json`** — written by `/mcp disable <server>` (undo with `/mcp enable`). Per project. `claude mcp remove` deletes rather than disables, so don't use it
- **`disableBundledSkills`** (bool) — drops all bundled skills and workflows at once. Too coarse, so normally not used

## Limits of verification (what can't be measured)

- **`name-only` can't be verified headless.** Headless (`claude -p`) doesn't show descriptions in the skills list to begin with (only `- coderabbit:code-review`). To check, restart an interactive session and look at `/context`
- **Account-side skills (`small-business:*` / `anthropic-skills:*` / `design:*`, etc.) don't appear headless**, so you can't measure headless whether an override worked. They aren't on disk either, so they don't show in `inventory.py`. Pick them up from the agent's own skills list and confirm the effect with `/context` after a restart
- **`/context` is a slash command, so it can't be run from a non-interactive session.** Ask the user to run it and paste the output

## About writing

Writes to `.claude/settings.json` **may be denied by the classifier** when the permission mode is `auto` (`Permission for this action was denied by the Claude Code auto mode classifier`). It isn't a structural block in the harness, so if denied:

1. Tell the user the permission mode (`permissions.defaultMode` in `~/.claude/settings.json`)
2. Write the finished file to the scratchpad and give them a `cp` command

Don't try to work around it. Settings changes are for the user to approve.
