---
name: setup
description: Build or update the agent-bridge (the shared message queue other AI agents and Claude Code talk through) in the user's Supabase project, add a participant agent, or check which secrets still hold placeholders. Uses a Supabase connector to apply the schema, register participants with placeholder Vault secrets the user replaces later, and deploy the Edge Function. Use for "set up the agent bridge", "add an agent to the bridge", "is the bridge configured", or in Japanese 「ブリッジをセットアップして」「エージェントを追加して」「ブリッジの設定を確認して」「Supabase にブリッジを作って」.
---

# agent-bridge setup

Builds the bridge inside a Supabase project the user already has, through a Supabase connector. **Never puts a real secret in the chat**: every secret is created in Vault as the placeholder `REPLACE_ME`, and the user replaces it in the Supabase dashboard (or, only when they ask, through the shell route in section 4, where Claude never sees the value).

Saved settings: connector = `${user_config.supabase_connector}`, project = `${user_config.supabase_project_id}`, bridge URL = `${user_config.bridge_url}`, this agent = `${user_config.agent_id}`. A value that still reads as a `${user_config...}` placeholder counts as empty.

## Modes

Pick from the request: **install** (first time or update), **add** (a participant), **check** (doctor). When unsure, run check first: it shows what exists.

## 1. Find the connector and project (all modes)

- Find a connector **by what it can do**, not by its name: tools that run SQL (`execute_sql(project_id, query)`), apply a migration (`apply_migration(project_id, name, query)`) and deploy an Edge Function (`deploy_edge_function(project_id, name, entrypoint_path, verify_jwt, files)`). With a saved connector, use it. Without one, list projects (`list_projects`) and ask the user which project to use.
- If no such connector is available, stop and tell the user to connect Supabase (claude.ai connector or MCP server). Don't fall back to something else.
- Save with `claude plugin configure agent-bridge@shibamasa-plugins --values-stdin` (the id from `claude plugin list` if it came from another marketplace) and JSON on stdin, for example `{"supabase_connector":"<server>","supabase_project_id":"<id>"}`. Where you can't run the `claude` CLI, ask the user to set them in the plugin's settings.

## 2. Install or update

**Ask first** (skip what the saved settings or the request already answer):

- **Install scope**: which repo's sessions should use the bridge. Plugin options are per user, so a user-scope install runs the hooks and the MCP server in every Claude Code session on the machine. For one repo, run from that repo `claude plugin install <plugin id> --scope local` (only you, this repo) or `--scope project` (everyone who uses the repo). When the plugin is already installed at user scope and the user wants one repo, `claude plugin uninstall <plugin id> --scope user` first, then install from that repo and save the settings again with `claude plugin configure`. The plugin id is the one from `claude plugin list`.
- **This environment's `agent_id`**: the id Claude Code in this environment uses on the bridge. Don't silently register `claude`; a second machine or repo needs its own id, and the user picks it. Save it with `claude plugin configure`.

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
5. Register Claude Code itself as a participant (add mode, `wake = poll`, `agent_id` from the saved setting), then continue with add mode for the other agents the user names.

## 3. Add a participant

Ask for: `agent_id` (lowercase letters, digits, `_` and `-`), a display name, its role and what it is good at (the user decides these; don't invent them), and how it is woken:

- `webhook`: the bridge POSTs each message to the agent's URL with `Authorization: Bearer <key>` and a JSON body `{"event":"agent_bridge.message","id","thread","from","to","body","created_at"}`. That body leaves Supabase for the agent's service; say so.
- `poll`: the agent checks `GET <bridge_url>?agent=<id>` on its own schedule and reads with its token.

Run `execute_sql`: `SELECT agent_bridge.register_participant('<id>', '<poll|webhook>', '<display name>', '<role>', '<capabilities>')` with every `'` in a value doubled. It creates the agent's missing Vault secrets as `REPLACE_ME` and never changes an existing one, so running it again keeps the user's values.

## 4. Hand the secrets to the user

Tell the user, per participant, which Vault secrets to replace in the Supabase dashboard (Project Settings → Vault, or Integrations → Vault, depending on the dashboard version):

- `agent_bridge:<id>:token`: a long random value the user makes themselves, for example with `openssl rand -hex 32` in their own terminal. The agent sends it as `Authorization: Bearer <token>`. For Claude Code, the same value goes into this plugin's `token` setting (the user enters it in the plugin's settings; it is stored in secure storage). **On this default path, don't generate it, ask for it, or echo it in the chat.**
- `agent_bridge:<id>:webhook_url` and `agent_bridge:<id>:webhook_key` (webhook agents): the agent service's webhook URL and the key it expects.

### Optional: Claude sets the token without seeing it

Offer this only when the user asks Claude to do the token handoff, and run it only after they explicitly say yes to the hosted write (it changes a Vault secret in their Supabase project; say which project, and that it is production when it is). **Never put the value in a connector tool call (`execute_sql` and the like), in a command's output or in the chat**: the connector route makes Claude read it, and the auto-mode check blocks that as a leak. Do everything in the shell, with files only the user can read, in the session scratchpad (`<scratch>`):

1. Generate it: `umask 077; openssl rand -hex 32 > <scratch>/tok`
2. Save it as the plugin's setting: `jq -n --rawfile t <scratch>/tok '{token:($t|rtrimstr("\n"))}' | claude plugin configure <plugin id> --values-stdin`
3. Build the SQL inside the shell, never printing it: `umask 077; { printf "SELECT vault.update_secret((SELECT id FROM vault.secrets WHERE name='agent_bridge:<id>:token'), '"; tr -d '\n' < <scratch>/tok; printf "') IS NULL AS updated;\n"; } > <scratch>/q.sql`
4. Run it with the user's logged-in Supabase CLI (3.x): `supabase db query --remote=<project-ref> --yes -f <scratch>/q.sql 2>&1 | grep -o '"updated"[^,}]*'`. Without `--yes` the CLI refuses in agent mode (`HostedMutationConsentRequiredError`), so `--yes` is the user's explicit OK, not a default. The filter keeps the value out of the output; when it prints nothing, treat that as a failure and don't show the raw output.
5. Delete both files: `rm -f <scratch>/q.sql`. Keep `<scratch>/tok` until check mode has run in step 5 of this skill (it needs it), then `rm -f <scratch>/tok`.

When the CLI is missing or logged out, copy the value instead: `pbcopy < <scratch>/tok` (macOS), and the user pastes it into the Vault secret in the dashboard, then delete `tok`. Without a clipboard tool, fall back to the manual steps above.

Until a secret is replaced, the bridge treats it as unset: a placeholder token authenticates no one, and a webhook agent's messages are stored with `delivery = not_configured` instead of being POSTed.

## 5. Check (doctor)

`execute_sql`: `SELECT * FROM agent_bridge.doctor()`. It lists, per participant, each secret's state: `set`, `placeholder` or `missing`, never a value. Then check the endpoint with a plain `GET <bridge_url>?agent=<this agent>` (for example `curl -s`), which should return `{"agent":...,"unread":...,"latest_id":...}`. Neither proves that the plugin's `token` equals the Vault secret. To prove it, make an authenticated call and read `me` in the answer, which must be this agent's id:

- In a session started after the settings were saved, call the `list_participants` tool.
- Right after Claude saved the token itself (section 4), the MCP server still has the old settings, so call the bridge from the shell with the token kept out of argv: `umask 077; printf 'Authorization: Bearer %s' "$(tr -d '\n' < <scratch>/tok)" > <scratch>/hdr`, then `curl -s -X POST <bridge_url> -H @<scratch>/hdr -H 'Content-Type: application/json' -d '{"action":"participants"}'`, then `rm -f <scratch>/hdr`.

`unauthorized` means the two values differ. Report all of it, and what the user still has to replace.

## Raising a thread's message cap

Each thread stops at `max_messages` (20 by default). Raise it only when the user asks: `UPDATE agent_bridge.threads SET max_messages = <n> WHERE thread_id = '<thread>'`.

## Finish

Plugin settings take effect only in a new Claude Code session (the MCP server and hooks read them at start). Tell the user to open one in the repo where the plugin is installed before using the bridge.
