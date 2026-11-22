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
- **whether the agent should answer.** A poll agent always reads with its token, so it can answer. A webhook agent that only receives needs no bridge token; one that answers (`send`, `ack`) does. A routine first built as "receive and report only" never replies until its instructions are replaced with the answering version (section 5).
- for a webhook agent: **who checks the bearer key**, the agent's platform (it verifies the header before the routine runs, so the agent needs no copy of the key) or the agent itself (it compares the header with a key it holds). This picks the variant in `instructions-webhook.md`.
- **whether the agent already has an earlier proof-of-concept route** (for example a public notification topic it reads or posts to). Plan to retire it once the bridge works (section 6, last step).

## 3. Register

Tell the user what will be created (a participant row and its Vault secrets as `REPLACE_ME`) and which project, and get a yes. Then run `execute_sql`: `SELECT agent_bridge.register_participant('<id>', '<poll|webhook>', '<display name>', '<role>', '<capabilities>')` with every `'` in a value doubled. It creates the agent's missing Vault secrets as `REPLACE_ME` and never changes an existing one, so running it again keeps the user's values.

## 4. Hand over the token

The token is a long random value. It goes into **two places**: the Vault secret `agent_bridge:<id>:token`, and the other agent's own secret store (an env file with mode 600, the platform's secret store, and the like). It does not go into this plugin's settings.

Default path: tell the user to make the value themselves in their own terminal (`openssl rand -hex 32`), paste it into the Vault secret in the Supabase dashboard (see "Where the Vault secrets are edited" below) and into the agent's store. **Don't generate it, ask for it, or echo it in the chat.** A webhook agent that only receives needs no token; skip the token and keep the two webhook values.

A webhook agent also needs `agent_bridge:<id>:webhook_url` and `agent_bridge:<id>:webhook_key` in Vault. **Both come from the agent's platform**: a hosted webhook routine usually shows its own POST URL, a key, and a ready-made `Authorization: Bearer …` header. Claude does not generate a webhook key in that case, and doesn't ask for it in the chat. People often mix up where to copy from and where to paste, so give the user this table:

| Value | Copy it from | Paste it into |
|---|---|---|
| Webhook URL | the agent platform's webhook page (its POST URL) | Vault secret `agent_bridge:<id>:webhook_url` |
| Webhook key | the same page: the **key**, not the ready-made `Authorization` header field | Vault secret `agent_bridge:<id>:webhook_key` |
| Bridge token | nowhere: the user's terminal makes it (`openssl rand -hex 32`), or the shell route below | Vault secret `agent_bridge:<id>:token`, and the agent's own secret input (section 5) |

Only when the platform asks the user to supply the key does the user make one, and then it goes into both places. When the platform checks the key itself (section 2), the agent needs no copy of it.

### Where the Vault secrets are edited

`https://supabase.com/dashboard/project/<project-ref>/integrations/vault/secrets?search=<id>` lists the agent's secrets (the project ref is the project id). Each row's ⋮ menu is at the far right, so scroll horizontally if it is out of view; choose Edit, replace the value, save. Without this URL, Project Settings → Vault or Integrations → Vault, depending on the dashboard version.

### Optional: Claude writes the Vault secret without seeing the token

Only when the user asks. Follow `${CLAUDE_PLUGIN_ROOT}/references/token-route.md` (`<id>` is the new agent's id). **With several agents, do one at a time**: the user pastes each token into its agent before the next one is made. Then get the value into the agent's store without Claude reading it, depending on where the store is:

- the agent's own chat with a secret-input card (section 5): `pbcopy < <scratch>/tok` (macOS), and the user pastes it into the card.
- an env file on another host: `umask 077; { printf 'AGENT_BRIDGE_TOKEN='; tr -d '\n' < <scratch>/tok; printf '\n'; } > <scratch>/agent.env`, then `scp <scratch>/agent.env <user>@<host>:<path>` and `chmod 600 <path>` there. Run the `scp` yourself only when the user names the host and path and says yes; otherwise give them the command.
- another platform secret store with a web form: `pbcopy < <scratch>/tok`, and the user pastes it there.

Claude never types a token into any page or chat. Delete `<scratch>/agent.env` after the copy. Keep `<scratch>/tok` until the agent itself has confirmed `me` (section 6), then delete it.

## 5. Write the instructions for the agent

The agent can't use the bridge until it is told how. Read the template that matches how it is woken, fill in the `{{...}}` values (id, `bridge_url`, the token's environment variable name, and for a webhook agent the key's), choose the variants the template lists, and give the user the text to paste into the agent's own instructions:

- poll: `${CLAUDE_PLUGIN_ROOT}/skills/add/references/instructions-poll.md`
- webhook: `${CLAUDE_PLUGIN_ROOT}/skills/add/references/instructions-webhook.md`

The `{{spec_line}}` is optional: a link to this plugin's README (`https://github.com/shibamasa-dev/claude-code-plugins/tree/main/plugins/agent-bridge`) for an agent that can read the web. Before handing the text over, check that it holds no secret, no `{{` left over, and **no angle-bracket placeholders** (`<URL>` and the like): one chat UI stripped them as markup. Every URL is written out in full.

**Hand the token over through the agent's own chat** when the agent has one: send the instruction text and ask for the agent's secret-input card in the same message. The user pastes the token into that card; Claude never types it. The text already says the token is a per-agent bearer token for the bridge's Edge Function, not a Supabase API key (an agent asked exactly that). The agent may store it as a credential bound to the bridge's host instead of an environment variable; the templates allow both. Some platforms then ask once per host: allow once, always, or deny. A poll agent needs **always**, or every check asks again.

Put the request format in the same message as the token (the templates do). One agent probed the bridge before it had instructions, got HTTP 400 `agent must match ^[a-z0-9_-]{1,40}$` and read it as "token accepted". That check runs before authentication, so a 400 proves nothing; the only proof is `{"action":"participants"}` answering with `me` equal to the agent's id.

## 6. Verify

1. `execute_sql`: `SELECT * FROM agent_bridge.doctor()`. The new agent's secrets show `set`, `placeholder` or `missing`, never a value. Report which ones the user still has to replace.
2. The new agent is listed: call the `list_participants` tool (Claude Code's own token), or read `participants` in the authenticated call of step 3.
3. The token. Ask the agent to call `{"action":"participants"}` and report `me`, which must be `<new id>`; the first call can take about 30 seconds (the Edge Function starts cold). When Claude holds `<scratch>/tok`, it can make the same call from `${CLAUDE_PLUGIN_ROOT}/references/token-route.md` (Authenticated call from the shell); `unauthorized` means the Vault secret differs from `tok`. Only after the agent itself has confirmed `me`: `rm -f <scratch>/tok <scratch>/agent.env`.
4. A test message, with no token exposed. The sender is Claude Code's own agent (`${user_config.agent_id}`); its token stays in Vault and the call reads it server-side. `execute_sql`:

   `SELECT agent_bridge.api(agent_bridge.secret('agent_bridge:<sender>:token'), 'send', jsonb_build_object('to', '<new id>', 'thread', 'setup-test-<new id>', 'body', '<test text>'))`

   (`api(token, action, args)` is the function every authenticated call goes through, defined in `bridge/migrations/0001_init.sql`.) It returns `{id, thread, to, delivery}`. Read the outcome without printing secrets:
   - the message and any reply: `SELECT id, from_agent, to_agent, delivery, claimed_at, read_at FROM agent_bridge.messages WHERE thread_id = 'setup-test-<new id>' ORDER BY id`. For a poll agent, `SELECT agent_bridge.status('<new id>')` shows its unread count.
   - a webhook agent's `delivery` stays `queued` even after a successful POST. The HTTP result is in `net._http_response`, matched by `messages.request_id`: `SELECT m.id, h.status_code, h.timed_out, h.error_msg FROM agent_bridge.messages m LEFT JOIN net._http_response h ON h.id = m.request_id WHERE m.id = <message id>`. A 2xx `status_code` means the platform accepted the POST, not that the routine ran. No row yet means pending (pg_net sends after the commit) or older than pg_net keeps. The same fields come back as `webhook_status`, `webhook_timed_out` and `webhook_error` from `api(<sender's token>, 'message', {"id": <message id>})`.

   Tell the owner that an agent following the "ask your owner first" rule may wait for their approval before it replies. That is expected, not a failure.
5. If the agent had an earlier proof-of-concept route (section 2), ask whether to retire it now that the bridge works.
