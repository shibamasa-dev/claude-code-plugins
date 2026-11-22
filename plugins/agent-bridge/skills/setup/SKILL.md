---
name: setup
description: Build or update the agent-bridge (the shared message queue other AI agents and Claude Code talk through) in the user's Supabase project, or check which secrets still hold placeholders. Uses a Supabase connector to apply the schema, register Claude Code with placeholder Vault secrets the user replaces later, and deploy the Edge Function. Adding another agent is the `add` skill. Use for "set up the agent bridge", "is the bridge configured", or in Japanese 「ブリッジをセットアップして」「ブリッジの設定を確認して」「Supabase にブリッジを作って」.
---

# agent-bridge setup

Builds the bridge inside a Supabase project the user already has, through a Supabase connector. **Never puts a real secret in the chat**: every secret is created in Vault as the placeholder `REPLACE_ME`, and the user replaces it in the Supabase dashboard (or, only when they ask, through the shell route in section 3, where Claude never sees the value).

Saved settings: connector = `${user_config.supabase_connector}`, project = `${user_config.supabase_project_id}`, bridge URL = `${user_config.bridge_url}`, this agent = `${user_config.agent_id}`. A value that still reads as a `${user_config...}` placeholder counts as empty.

## Modes

Pick from the request: **install** (first time or update) or **check** (doctor). Connecting another agent is the `add` skill. When unsure, run check first: it shows what exists.

## 1. Find the connector and project (all modes)

Follow `${CLAUDE_PLUGIN_ROOT}/references/connector.md`.

## 2. Install or update

**Ask first** (skip what the request already answers, or a saved setting the user chose; a saved `agent_id` of `claude` is the default, not an answer, so ask unless the user named it):

- **Install scope**: which repo's sessions should use the bridge. Plugin options (`agent_id`, `token`, `bridge_url`) are saved per user whatever the scope, so the scope decides only where the hooks and the MCP server run: a user-scope install runs them in every Claude Code session on the machine. For one repo, run from that repo `claude plugin install <plugin id> --scope local` (only you, this repo) or `--scope project` (everyone who uses the repo). When the plugin is already installed at user scope and the user wants one repo, `claude plugin uninstall <plugin id> --scope user` first, then install from that repo and save the settings again with `claude plugin configure`. The plugin id is the one from `claude plugin list`.
- **This environment's `agent_id`**: the id Claude Code in this environment uses on the bridge. Don't silently register `claude`; each machine or user that connects needs its own id, and the user picks it. The id is per user, not per repo: every repo on this machine where the plugin is enabled uses the same one. Save it with `claude plugin configure`.

**Before changing anything, tell the user exactly what will be created and get a yes:**

- the `pg_net` extension (if missing) and a schema `agent_bridge` with tables `participants`, `threads`, `messages`, `schema_migrations`, triggers and functions. Nothing goes into `public`; the Data API roles get no access
- an Edge Function `agent-bridge` with **JWT verification off**. It checks a per-agent token itself. Its unauthenticated `GET ?agent=<id>` returns only a count and the newest message id for that agent, so anyone who knows the URL can see how many messages an agent has, never their content
- each call to the function and each webhook delivery counts toward the project's usage; the function holds at most one database connection per instance
- which project it is: if it is the user's production project (the connector or the Supabase CLI says so), say that in this message

Then:

1. Check what is applied: `execute_sql`: `SELECT version FROM agent_bridge.schema_migrations ORDER BY version`. An error saying the schema does not exist means nothing is applied.
2. For each file in `${CLAUDE_PLUGIN_ROOT}/bridge/migrations/` (in name order) whose name (without `.sql`) is not in that list, read it and run `apply_migration` with name `agent_bridge_<file name without .sql>` and the file's text as the query. The files are idempotent, so re-running one is harmless.
3. Deploy the function: read `${CLAUDE_PLUGIN_ROOT}/bridge/functions/agent-bridge/index.ts` and `router.mjs`, then `deploy_edge_function` with name `agent-bridge`, entrypoint `index.ts`, `verify_jwt: false`, and both files under their own names. Deploying again replaces the function.
4. The URL is `https://<project-ref>.supabase.co/functions/v1/agent-bridge` (the project ref is the project id). Save it as `bridge_url`.
5. Register Claude Code itself as a participant with the `add` skill's registration step (`wake = poll`, `agent_id` from the saved setting). Tell the user that connecting other agents is the `add` skill.

## 3. Hand over Claude Code's token

Tell the user which Vault secret to replace in the Supabase dashboard (`https://supabase.com/dashboard/project/<project-ref>/integrations/vault/secrets?search=<agent_id>`; each row's ⋮ menu at the far right, then Edit; older dashboards: Project Settings → Vault or Integrations → Vault): `agent_bridge:<agent_id>:token`, a long random value the user makes themselves, for example with `openssl rand -hex 32` in their own terminal. Claude Code sends it as `Authorization: Bearer <token>`, and the same value goes into this plugin's `token` setting (the user enters it in the plugin's settings; it is stored in secure storage). **On this default path, don't generate it, ask for it, or echo it in the chat.**

### Optional: Claude sets the token without seeing it

Follow `${CLAUDE_PLUGIN_ROOT}/references/token-route.md` with `<id>` = the saved `agent_id`. Its step 2 here is saving the value as the plugin's setting: `jq -n --rawfile t <scratch>/tok '{token:($t|rtrimstr("\n"))}' | claude plugin configure <plugin id> --values-stdin`.

Until the secret is replaced, a placeholder token authenticates no one.

## 4. Check (doctor)

`execute_sql`: `SELECT * FROM agent_bridge.doctor()`. It lists, per participant, each secret's state: `set`, `placeholder` or `missing`, never a value. Then check the endpoint with a plain `GET <bridge_url>?agent=<this agent>` (for example `curl -s`), which should return `{"agent":...,"unread":...,"latest_id":...}`. Neither proves that the plugin's `token` equals the Vault secret. To prove it, make an authenticated call and read `me` in the answer, which must be this agent's id:

- In a session started after the settings were saved, call the `list_participants` tool.
- Right after Claude saved the token itself (section 3), the MCP server still has the old settings, so make the authenticated call from the shell (Authenticated call from the shell in `${CLAUDE_PLUGIN_ROOT}/references/token-route.md`), then delete `<scratch>/tok`.

`unauthorized` means the two values differ. The shell call proves only that the Vault secret equals `tok`; the saved plugin setting is proved only by `list_participants` in a new session, so until then report the plugin side as unverified. Report all of it, and what the user still has to replace.

## Raising a thread's message cap

Each thread stops at `max_messages` (20 by default). Raise it only when the user asks: `UPDATE agent_bridge.threads SET max_messages = <n> WHERE thread_id = '<thread>'`.

## Finish

Plugin settings take effect only in a new Claude Code session (the MCP server and hooks read them at start). Tell the user to open one in the repo where the plugin is installed before using the bridge.
