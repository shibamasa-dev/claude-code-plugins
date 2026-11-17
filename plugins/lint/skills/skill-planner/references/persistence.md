# Skill Persistence

Use persistence only when it materially improves future runs.

## Where state lives

Never write state into the skill's own directory. In a plugin, the plugin root is replaced on update, so anything stored there is lost. Two cases:

- **Skill shipped in a plugin**: state goes under `${CLAUDE_PLUGIN_DATA}` (the plugin's persistent data directory), so the skill works with no setup. Say in the README that uninstalling the plugin from the last place it is installed deletes that directory, and a SQLite database inside it, unless `--keep-data` is passed.
- **Standalone skill** (personal or project skill, no plugin): that variable does not exist. Keep state at a path the user chooses, outside the skill directory, and document it.

Either way:

- Let users move it: offer a setting such as `sqlite_path` (a `userConfig` option in a plugin). A database outside the plugin data directory is not touched on uninstall.
- Remote store (Postgres, Supabase, Turso): the connection string is a secret. In a plugin it is a `sensitive` `userConfig` option (`database_url`). Such a value is substituted into MCP/LSP server config and exec-form hook args and exported to hooks as `CLAUDE_PLUGIN_OPTION_<KEY>`; skill text gets a placeholder and commands run through Bash get nothing (see the userConfig section of https://code.claude.com/docs/en/plugins-reference). So plan for it: a CLI that the skill runs through Bash cannot read the value, and a direct remote store needs an MCP server bundled with the plugin as the runner (the value goes in its `env`), or a connector route instead. A standalone skill uses an environment variable or a secret manager.
- Schema changes apply automatically and idempotently; never ask the user to run an `ALTER` by hand.
- Decide the store once and save the choice. When it is unavailable, stop and say so; never fall back to another store, or the data splits across two places.

## Local Persistence

Use SQLite or local files for state that belongs to one machine:

- history
- indexes
- caches
- run records
- queues
- eval results
- user-approved local preferences

Document:

- database or state path
- schema version
- migration or recreate policy
- backup/export command
- reset command
- what is stored and why

Do not store:

- secrets
- temporary chatter
- private user memory that belongs in Claude's own memory
- stale facts likely to become wrong
- large external research better served by a searchable knowledge store

## Remote Persistence

Consider Postgres, Supabase, Turso or another remote database only when state must work across environments, machines, or deployments.

Document:

- setup steps
- credential configuration
- schema creation and migration
- behavior when two writers collide
- behavior when the store is unavailable (stop and report; see the rule below)
- data boundaries
- delete/export behavior

Rules:

- Do not commit credentials.
- Do not create remote schema or write data without explicit user approval.
- When credentials or network are unavailable, stop and report that the store is unavailable. Never fall back to another store (no local copy, no cache that accepts writes); reads come only from the configured store.

## Data Boundary

Every persistent skill should answer:

- What is stored?
- Why is it stored?
- Who or what can read it?
- How is it updated?
- How is it deleted?
- How is it exported?
- What happens when the store is unavailable?
