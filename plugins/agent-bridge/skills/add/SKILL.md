---
name: add
description: Connect another AI agent to the agent-bridge (the shared message queue on the user's Supabase project) - register it as a participant, hand over its token, and write the instructions that agent needs to use the bridge. Use for "add an agent to the bridge", "connect <agent> to the bridge", "write the instructions to give <agent>", or in Japanese 「エージェントを追加して」「〜をブリッジにつないで」「〜に渡す指示を作って」. Needs a bridge that setup already built.
---

# agent-bridge: add an agent

Connects one agent to a bridge that already exists. If the bridge isn't built yet (no `agent_bridge` schema), use the `setup` skill first. **Never puts a real secret in the chat**: the agent's secrets are created in Vault as the placeholder `REPLACE_ME`, and the user replaces them (or, only when they ask, uses the shell route in section 4, where Claude never sees the value).

Saved settings: connector = `${user_config.supabase_connector}`, project = `${user_config.supabase_project_id}`, bridge URL = `${user_config.bridge_url}`. A value that still reads as a `${user_config...}` placeholder counts as empty.

## 1. Find the connector and project

Follow `${CLAUDE_PLUGIN_ROOT}/references/connector.md`.

## 2. Ask

The user decides these; don't invent them:

- `agent_id`: lowercase letters, digits, `_` and `-`, up to 40 characters
- a display name, its role, and what it is good at
- how the agent is woken. If the user doesn't know, ask two questions: does the agent have an HTTPS address the bridge can POST to (→ `webhook`), or can it only run on a schedule or on request (→ `poll`)?
  - `webhook`: the bridge POSTs each message to the agent's URL with `Authorization: Bearer <key>` and a JSON body `{"event":"agent_bridge.message","id","thread","from","to","body","created_at"}`. **That body leaves Supabase for the agent's service; say so.**
  - `poll`: the agent checks `GET <bridge_url>?agent=<id>` on its own schedule and reads with its token.

## 3. Register

Tell the user what will be created (a participant row and its Vault secrets as `REPLACE_ME`) and which project, and get a yes. Then run `execute_sql`: `SELECT agent_bridge.register_participant('<id>', '<poll|webhook>', '<display name>', '<role>', '<capabilities>')` with every `'` in a value doubled. It creates the agent's missing Vault secrets as `REPLACE_ME` and never changes an existing one, so running it again keeps the user's values.

## 4. Hand over the token

The token is a long random value. It goes into **two places**: the Vault secret `agent_bridge:<id>:token`, and the other agent's own secret store (an env file with mode 600, the platform's secret store, and the like). It does not go into this plugin's settings.

Default path: tell the user to make the value themselves in their own terminal (`openssl rand -hex 32`), paste it into the Vault secret in the Supabase dashboard (Project Settings → Vault, or Integrations → Vault, depending on the dashboard version) and into the agent's store. **Don't generate it, ask for it, or echo it in the chat.**

A webhook agent also needs `agent_bridge:<id>:webhook_url` and `agent_bridge:<id>:webhook_key` in Vault: the agent service's webhook URL and the key it expects. The user gets them from that service and replaces both in the dashboard; don't ask for the key in the chat. The agent keeps its own copy of the key to check incoming requests.

### Optional: Claude writes the Vault secret without seeing the token

Only when the user asks. Follow `${CLAUDE_PLUGIN_ROOT}/references/token-route.md` (`<id>` is the new agent's id). Then get the value into the agent's store without Claude reading it, depending on where the store is:

- an env file on another host: `umask 077; { printf 'AGENT_BRIDGE_TOKEN='; tr -d '\n' < <scratch>/tok; printf '\n'; } > <scratch>/agent.env`, then `scp <scratch>/agent.env <user>@<host>:<path>` and `chmod 600 <path>` there. Run the `scp` yourself only when the user names the host and path and says yes; otherwise give them the command.
- a platform secret store with a web form: `pbcopy < <scratch>/tok` (macOS), and the user pastes it there.

Delete `<scratch>/agent.env` and, after section 6, `<scratch>/tok`.

## 5. Write the instructions for the agent

The agent can't use the bridge until it is told how. Read the template that matches how it is woken, fill in the `{{...}}` values (id, `bridge_url`, the token's environment variable name, and for a webhook agent the key's), and give the user the text to paste into the agent's own instructions:

- poll: `${CLAUDE_PLUGIN_ROOT}/skills/add/references/instructions-poll.md`
- webhook: `${CLAUDE_PLUGIN_ROOT}/skills/add/references/instructions-webhook.md`

The `{{spec_line}}` is optional: a link to this plugin's README (`https://github.com/shibamasa-dev/claude-code-plugins/tree/main/plugins/agent-bridge`) for an agent that can read the web. The text holds no secret; check that before handing it over.

## 6. Verify

1. `execute_sql`: `SELECT * FROM agent_bridge.doctor()`. The new agent's secrets show `set`, `placeholder` or `missing`, never a value. Report which ones the user still has to replace.
2. The new agent is listed: call the `list_participants` tool (Claude Code's own token), or read `participants` in the authenticated call of step 3.
3. When Claude holds `<scratch>/tok`, make the authenticated call from `${CLAUDE_PLUGIN_ROOT}/references/token-route.md` (Authenticated call from the shell). The answer's `me` must be `<new id>`; `unauthorized` means the Vault secret differs from `tok`. Then `rm -f <scratch>/tok <scratch>/agent.env`.

Without the token file, say that the token is unverified until the agent makes its first authenticated call.
