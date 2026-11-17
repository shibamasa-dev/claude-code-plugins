# Skill Persistence

Use persistence only when it materially improves future runs.

## Where state lives

Never write state into the skill's own directory. A plugin's skill directory is read-only and is replaced on update, so state there is lost or the write fails.

- Default: SQLite or files under `${CLAUDE_PLUGIN_DATA}`, so the skill works with no setup. Say in the README that uninstalling the plugin from the last place it is installed deletes `${CLAUDE_PLUGIN_DATA}` (and a SQLite database inside it) unless `--keep-data` is passed.
- Let users move it: offer a `userConfig` option such as `sqlite_path`. A database outside `${CLAUDE_PLUGIN_DATA}` is not touched on uninstall.
- Remote (Postgres, Supabase, Turso): take the connection string as a `sensitive` `userConfig` option (`database_url`), never from a file in the skill.
- A skill that is not shipped in a plugin (a personal skill) still keeps state outside its own directory, in a documented path of the user's choosing.
- Schema changes apply automatically and idempotently; never ask the user to run an `ALTER` by hand.
- Decide the store once, save the choice in `userConfig`, and when it is unavailable stop and say so instead of falling back to another store (the data would split across two places).

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
- sync behavior
- offline behavior
- conflict behavior
- data boundaries
- delete/export behavior

Rules:

- Do not commit credentials.
- Do not create remote schema or sync data without explicit user approval.
- Degrade gracefully when credentials or network are unavailable.
- Prefer a local fallback or read-only mode when practical.

## Data Boundary

Every persistent skill should answer:

- What is stored?
- Why is it stored?
- Who or what can read it?
- How is it updated?
- How is it deleted?
- How is it exported?
- What happens when the store is unavailable?
