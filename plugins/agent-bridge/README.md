# agent-bridge

English | [日本語](README.ja.md)

Two-way messaging between Claude Code and other AI agents through a message queue you host in your own Supabase project. Every agent uses the same small HTTP API with its own token. Each agent is woken in one of two ways: the bridge POSTs new messages to its webhook, or the agent polls. A listening Claude Code session wakes up when a message arrives.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install agent-bridge@shibamasa-plugins
```

Then ask Claude to "set up the agent bridge". The `setup` skill builds the bridge in a Supabase project you choose. To connect another agent, ask Claude to "add an agent to the bridge": the `add` skill registers it, hands over its token and writes the instructions you give that agent.

## How it works

```text
Claude Code (this plugin) ─┐                        ┌─> webhook agent   (the bridge POSTs each message to it)
other agent with a token ──┼─> Edge Function ─> DB ─┤
                           │   agent-bridge         └─> poll agent      (checks GET ?agent=<id>, then reads)
```

- **The bridge** is a schema `agent_bridge` (participants, threads, messages) and an Edge Function `agent-bridge` in your Supabase project. Every rule lives in the schema: who a token belongs to, the per-thread message cap, claiming and acknowledging messages. The Data API roles get no access to the schema; only the Edge Function reaches it.
- **The API**: `POST <bridge_url>` with `Authorization: Bearer <token>` and `{"action": ...}`. The actions are `send` (`to`, `thread`, `body`, optional `purpose`), `inbox` (claims up to `limit` unread messages for 10 minutes), `ack` (`ids`), `participants` and `message` (`id`: delivery state). Errors come back as `{"error": "<code>", "message": ...}`: `unauthorized` (401), `bad_request` or `unknown_agent` (400), `not_found` (404), `hop_limit` or `thread_closed` (409).
- **Waking agents**: a `webhook` agent gets each message as a POST to its URL, with `Authorization: Bearer <its webhook key>` and the body `{"event":"agent_bridge.message","id","thread","from","to","body","created_at"}`. A `poll` agent calls `GET <bridge_url>?agent=<id>`, which needs no token and returns only `{"agent","unread","latest_id"}`, and reads with its token when `latest_id` or `unread` goes up. A message it claimed with `inbox` but did not `ack` comes back after 10 minutes without a new id, so while `unread` stays above 0, the agent calls `inbox` again from time to time.
- **Secrets** live in Supabase Vault: `agent_bridge:<id>:token` for every agent, plus `agent_bridge:<id>:webhook_url` and `:webhook_key` for webhook agents. Setup creates them as the placeholder `REPLACE_ME`, and you replace them in the dashboard. A placeholder token authenticates no one. A webhook agent whose secrets are placeholders gets its messages stored but not POSTed (`delivery: not_configured`).
- **Threads**: only an agent already in a thread (its creator, or one that sent or received a message in it) can write to it.
- **Capabilities**: each participant has a free-text `capabilities` field, such as the external services it is connected to and what it can do there (GitHub with push and PRs, accounts it can post to). Other agents use it to decide who to ask for what. `setup` and `add` ask for it. Change it later with `UPDATE agent_bridge.participants SET capabilities = '...' WHERE agent_id = '...'`. Running `register_participant` again also changes it, but it overwrites `wake`, `display_name`, `role` and `capabilities` together with the values you pass, so pass all four.
- **Loop guard**: a thread takes at most `max_messages` messages (20 by default). After that, sends fail with `hop_limit` until you raise the cap.

The bridge's data is shared by several agents on different machines, so it lives in Supabase only. Unlike this repo's other plugins that keep data, there is no local SQLite default: a local file could not be shared.

## What is sent where

- Message bodies are stored in your Supabase project's database.
- A message to a webhook agent is also sent to that agent's webhook URL, which is usually another company's service.
- Anyone who knows the bridge URL can read how many messages an agent has and the newest message id, but not the content.
- Claude treats message bodies as data from other agents, never as instructions from you, and asks before acting on a request in one.

## Skills

| Skill | Use it for |
|---|---|
| `setup` | Building or updating the bridge in your Supabase project, registering Claude Code, and checking which Vault secrets still hold placeholders. It shows what it will create and waits for your yes before changing anything |
| `add` | Connecting another agent: registering it as a participant (poll or webhook), handing over its token, writing the instructions you paste into that agent so it knows how to use the bridge, and checking it end to end with a test message ("add an agent to the bridge", "write the instructions to give the reviewer agent") |
| `talk` | Sending to and reading from other agents, and moderating a discussion between agents ("ask the reviewer agent", "check the inbox", "have them discuss X") |

## Tools

The bundled MCP server (`bridge`): `send_message`, `check_inbox`, `mark_read`, `list_participants`, `message_status`. Each is one HTTPS call to the bridge. Nothing is cached locally.

## Hooks

| Hook | When | What it does |
|---|---|---|
| `arm_session.py` | `PostToolUse` on the bridge's tools | Marks the session as one that talks to agents, so only such sessions listen |
| `wait_inbox.py` | `SessionStart` and `Stop`, in the background (`asyncRewake`) | With `listen` on, in a marked session: polls the bridge's status every `poll_seconds`. When a message is unread and either its id is newer than any this machine has seen for this bridge or the unread count went up, it wakes Claude with a count only (never the body). It records the id and count first, so one message wakes one session once. Stops `max_wait_minutes` after the session's last turn (a new turn extends a poller that is still running) or when its session's process is gone, and the next turn starts it again |
| `unread_notice.py` | `UserPromptSubmit` | When messages are unread, adds their count to your prompt's context. Silent when there are none or the bridge doesn't answer within 2 seconds |

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `bridge_url` | empty | The Edge Function URL (`https://<project-ref>.supabase.co/functions/v1/agent-bridge`). Setup fills it in. Empty means not set up: the tools return an error and the hooks do nothing |
| `agent_id` | `claude` | Claude Code's participant id on the bridge. Per user, not per repo; use a different id for each machine or user that connects |
| `token` | empty | Claude Code's token, the same value as the Vault secret `agent_bridge:<agent_id>:token`. Sensitive: kept in secure storage. You enter it yourself; Claude never sees it |
| `listen` | `false` | Wake sessions when a message arrives. Off by default. When on, an outside message starts a Claude turn (tokens, tool use), every poll costs an Edge Function call, and plugin options are per user, so with a user-scope install this covers every session on the machine (only sessions that have used a bridge tool poll). With it off, a running session notices a reply at its next prompt, which can be much later than the reply. `setup` asks whether this session should wake up when a message arrives |
| `poll_seconds` | `60` | Interval between status checks while listening (15 to 3600). Each check is one Edge Function call |
| `max_wait_minutes` | `50` | How long a listening session polls without a turn (1 to 55) |
| `supabase_connector`, `supabase_project_id` | empty | Saved by setup: the Supabase connector and project the bridge is in |

Install scope: to use the bridge in one repo only, install from that repo with `claude plugin install <plugin id> --scope local` (or `--scope project`) instead of `--scope user`; a user-scope install runs the hooks and the MCP server in every session on the machine. The scope decides only where the plugin runs: the options (`agent_id`, `token`, `bridge_url`) are saved per user whatever the scope, so every repo on the machine that has the plugin enabled uses the same ones. The `setup` skill asks for the scope and the `agent_id`.

Changing options: `echo '{"listen":"true"}' | claude plugin configure <plugin id> --values-stdin`. The command takes only string values, so write numbers and booleans as strings (`"60"`, `"true"`); a JSON boolean fails with "The input on stdin isn't a JSON object of strings". A plugin installed at local or project scope has to be configured from that project's folder; elsewhere it fails with `No installed plugin has the id ...`. New sessions read the options when they start. **Run `/reload-plugins` in every Claude Code session that is already running**: until then it keeps the old values, so its bridge tools can answer `agent-bridge is not configured` while its hooks already see the new settings, and a changed `listen` starts nothing. A running session also keeps the plugin version it loaded.

Polling cost: every check is one Edge Function call. Calls per day = 86400 / interval in seconds, and per month about 30 times that. One poller at 60 s makes about 1,440 calls a day (about 43,000 a month), and each polling agent or listening session adds its own. Compare the total with the Edge Function quota of your Supabase plan on Supabase's pricing page.

Seeing the data: everything is in the schema `agent_bridge`, not `public`, so the dashboard's Table Editor does not list it until you pick that schema, or open `https://supabase.com/dashboard/project/<project-ref>/editor?schema=agent_bridge`.

Files on this machine: under `${CLAUDE_PLUGIN_DATA}/wait/` (or `~/.claude/state/agent-bridge/wait/`) the hooks keep the newest message id and unread count seen per bridge and agent, one pid file per polling session and one mark per session that used a bridge tool. Pid files older than two days and marks unused for 14 days are removed. Uninstalling the plugin from the last place it is installed deletes `${CLAUDE_PLUGIN_DATA}` unless you pass `--keep-data`; the fallback `~/.claude/state/agent-bridge/` is outside it and stays, so delete it by hand. The bridge's data stays in your Supabase project; to remove it, drop the `agent_bridge` schema, the `agent-bridge` Edge Function and the `agent_bridge:*` Vault secrets.

## Limitations

- A listening session wakes only while Claude Code is running. When a poller stops after `max_wait_minutes` with no turn, new messages wait until your next prompt, where `unread_notice.py` reports them.
- Webhook delivery uses Supabase's `pg_net`, which sends after the message is stored and does not retry. `message_status` shows the HTTP status the agent's service returned. Supabase keeps that response for about 6 hours.
- The webhook payload and auth header are fixed (`Authorization: Bearer <key>`, JSON body). An agent service that needs another format needs its own adapter.
- `setup` and `add` need a Supabase connector that can run SQL, apply migrations and deploy Edge Functions.

## Requirements

- macOS or Linux (the hooks use `fcntl` and `ps`)
- `python3` (standard library only)
- A Supabase project with Vault and `pg_net` (both available on Supabase)
- For `setup` and `add`: a Supabase connector (claude.ai connector or MCP server)

## Tests

```bash
bash plugins/agent-bridge/tests/run-all.sh        # MCP server, hooks and Edge Function router (python3 and node, against a local fake bridge)
bash plugins/agent-bridge/tests/run-postgres.sh   # the schema on a throwaway postgres:16 container (docker, psql), with stand-ins for Vault and pg_net
```
