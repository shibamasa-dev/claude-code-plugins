---
name: setup
description: Build or update the agent-bridge (the shared message queue other AI agents and Claude Code talk through) in the user's Supabase project, add a participant agent, or check which secrets still hold placeholders. Uses a Supabase connector to apply the schema, register participants with placeholder Vault secrets the user replaces later, and deploy the Edge Function. Use for "set up the agent bridge", "add an agent to the bridge", "is the bridge configured", or in Japanese 「ブリッジをセットアップして」「エージェントを追加して」「ブリッジの設定を確認して」「Supabase にブリッジを作って」.
---

# agent-bridge setup

Builds the bridge inside a Supabase project the user already has, through a Supabase connector. **Never puts a real secret in the chat**: every secret is created in Vault as the placeholder `REPLACE_ME`, and the user replaces it in the Supabase dashboard.

Saved settings: connector = `${user_config.supabase_connector}`, project = `${user_config.supabase_project_id}`, bridge URL = `${user_config.bridge_url}`, this agent = `${user_config.agent_id}`. A value that still reads as a `${user_config...}` placeholder counts as empty.

## Modes

Pick from the request: **install** (first time or update), **add** (a participant), **check** (doctor). When unsure, run check first: it shows what exists.

## 1. Find the connector and project (all modes)

- Find a connector **by what it can do**, not by its name: tools that run SQL (`execute_sql(project_id, query)`), apply a migration (`apply_migration(project_id, name, query)`) and deploy an Edge Function (`deploy_edge_function(project_id, name, entrypoint_path, verify_jwt, files)`). With a saved connector, use it. Without one, list projects (`list_projects`) and ask the user which project to use.
- If no such connector is available, stop and tell the user to connect Supabase (claude.ai connector or MCP server). Don't fall back to something else.
- Save with `claude plugin configure agent-bridge@shibamasa-plugins --values-stdin` (the id from `claude plugin list` if it came from another marketplace) and JSON on stdin, for example `{"supabase_connector":"<server>","supabase_project_id":"<id>"}`. Where you can't run the `claude` CLI, ask the user to set them in the plugin's settings.

## 2. Install or update

**Before changing anything, tell the user exactly what will be created and get a yes:**

- the `pg_net` extension (if missing) and a schema `agent_bridge` with tables `participants`, `threads`, `messages`, `schema_migrations`, triggers and functions. Nothing goes into `public`; the Data API roles get no access
- an Edge Function `agent-bridge` with **JWT verification off**. It checks a per-agent token itself. Its unauthenticated `GET ?agent=<id>` returns only a count and the newest message id for that agent, so anyone who knows the URL can see how many messages an agent has, never their content
- each call to the function and each webhook delivery counts toward the project's usage; the function holds at most one database connection per instance

Then:

1. Check what is applied: `execute_sql`: `SELECT version FROM agent_bridge.schema_migrations ORDER BY version`. An error saying the schema does not exist means nothing is applied.
2. For each file in `${CLAUDE_PLUGIN_ROOT}/bridge/migrations/` (in name order) whose name (without `.sql`) is not in that list, read it and run `apply_migration` with name `agent_bridge_<file name without .sql>` and the file's text as the query. The files are idempotent, so re-running one is harmless.
3. Deploy the function: read `${CLAUDE_PLUGIN_ROOT}/bridge/functions/agent-bridge/index.ts` and `router.mjs`, then `deploy_edge_function` with name `agent-bridge`, entrypoint `index.ts`, `verify_jwt: false`, and both files under their own names. Deploying again replaces the function.
4. The URL is `https://<project-ref>.supabase.co/functions/v1/agent-bridge` (the project ref is the project id). Save it as `bridge_url`.
5. Register Claude Code itself as a participant (add mode, `wake = poll`, `agent_id` from the saved setting, `claude` if empty), then continue with add mode for the other agents the user names.

## 3. Add a participant

Ask for: `agent_id` (lowercase letters, digits, `_` and `-`), a display name, its role and what it is good at (the user decides these; don't invent them), and how it is woken:

- `webhook`: the bridge POSTs each message to the agent's URL with `Authorization: Bearer <key>` and a JSON body `{"event":"agent_bridge.message","id","thread","from","to","body","created_at"}`. That body leaves Supabase for the agent's service; say so.
- `poll`: the agent checks `GET <bridge_url>?agent=<id>` on its own schedule and reads with its token.

Run `execute_sql`: `SELECT agent_bridge.register_participant('<id>', '<poll|webhook>', '<display name>', '<role>', '<capabilities>')` with every `'` in a value doubled. It creates the agent's missing Vault secrets as `REPLACE_ME` and never changes an existing one, so running it again keeps the user's values.

## 4. Hand the secrets to the user

Tell the user, per participant, which Vault secrets to replace in the Supabase dashboard (Project Settings → Vault, or Integrations → Vault, depending on the dashboard version):

- `agent_bridge:<id>:token`: a long random value the user makes themselves, for example with `openssl rand -hex 32` in their own terminal. The agent sends it as `Authorization: Bearer <token>`. For Claude Code, the same value goes into this plugin's `token` setting (the user enters it in the plugin's settings; it is stored in secure storage). **Don't generate it, ask for it, or echo it in the chat.**
- `agent_bridge:<id>:webhook_url` and `agent_bridge:<id>:webhook_key` (webhook agents): the agent service's webhook URL and the key it expects.

Until a secret is replaced, the bridge treats it as unset: a placeholder token authenticates no one, and a webhook agent's messages are stored with `delivery = not_configured` instead of being POSTed.

## 5. Check (doctor)

`execute_sql`: `SELECT * FROM agent_bridge.doctor()`. It lists, per participant, each secret's state: `set`, `placeholder` or `missing`, never a value. Then check the endpoint with a plain `GET <bridge_url>?agent=<this agent>` (for example `curl -s`), which should return `{"agent":...,"unread":...,"latest_id":...}`. Report both, and what the user still has to replace.

## Raising a thread's message cap

Each thread stops at `max_messages` (20 by default). Raise it only when the user asks: `UPDATE agent_bridge.threads SET max_messages = <n> WHERE thread_id = '<thread>'`.
