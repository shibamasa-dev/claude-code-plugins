# claude-code-plugins-public

## References for building plugins and MCP servers

Verify spec questions against the official docs. The official plugin-dev skill (v0.1.0) is outdated: it doesn't cover `userConfig`, `mcp_tool` hooks, `${CLAUDE_PLUGIN_DATA}` or `.mcpb`, and it still suggests the old `.claude/<plugin>.local.md` settings files, so use it only as a skeleton. The mcp-builder skill reads the MCP spec but not Claude-side features such as MCP Apps.

1. Plugins: https://code.claude.com/docs/en/plugins-reference (plugin.json, `userConfig`, environment variables)
2. Hooks: https://code.claude.com/docs/en/hooks (`mcp_tool` hooks and more)
3. Settings: https://code.claude.com/docs/en/settings-reference (`pluginConfigs` and more)
4. Latest Claude Code changes: https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
5. MCP spec: https://modelcontextprotocol.io/specification/latest and https://blog.modelcontextprotocol.io
6. MCP connector in the API: https://platform.claude.com/docs/en/agents-and-tools/mcp-connector

Never write internal company values in this repo (organization-wide values are injected by the organization's own plugin). Take per-user values through `userConfig` and reference them as `${user_config.KEY}`.

## Language

This is a public repo for users worldwide, so English is the base language.

- Write in English: skill bodies and `references/`, hook and script messages, comments, tests, commands, `plugin.json` / `marketplace.json` descriptions and `userConfig` titles, new CHANGELOG entries, issue and PR templates, commit messages and PR titles
- Japanese goes only in `README.ja.md`. Nothing else gets a translation; Claude replies in the user's language anyway
- Exceptions where Japanese stays:
  - Skill `description` frontmatter: English first, then the Japanese trigger phrases (for example 「閉じたい」「残件確認して」). Triggering matches the language of the user's prompt, so dropping them breaks Japanese prompts
  - Data the feature needs: regexes or keywords that match Japanese text, fixtures and eval prompts that represent Japanese input, detectors that still accept an older Japanese marker
  - CHANGELOG entries written before the switch to English (don't rewrite history)
- Where a skill says which language to answer in, say "the user's language", not a fixed language

## READMEs

The layout follows Anthropic's plugin repos (anthropics/claude-plugins-official, anthropics/claude-code `plugins/`, anthropics/knowledge-work-plugins): one README at the root and one per plugin, no separate docs tree.

- Place: `README.md` at the root and in every `plugins/<name>/`, each with a `README.ja.md` next to it
- Line 3 of both files is the language switcher: `English | [日本語](README.ja.md)` in README.md, `[English](README.md) | 日本語` in README.ja.md. Links inside README.ja.md point to other `README.ja.md` files
- Change both files in the same PR, with the same sections in the same order
- Root README sections: title, switcher, badges, one-line purpose, a trust note (plugins run code on your machine), Install (`/plugin marketplace add` → `/plugin install`), Plugins table (name → what it does, linked to the plugin README), Language, Requirements, Contributing, License. Keep a migration section only while a rename is recent
- Plugin README sections, roughly in this order, omitting ones that don't apply: title, switcher, one-line summary, Install, Skills (skill / use it for), Hooks (hook / when / what it does), Mods, Commands, Configuration (`userConfig` keys: key / default / meaning, plus per-repo overrides), Limitations, Requirements, Tests
- Describe the current behavior only. Version history and reasons for past changes go in CHANGELOG.md
- `.github/scripts/check-repo.py` enforces the pair, the switcher links and the absence of kana in `README.md`

## PR reviews

review-heavy: coderabbit, codex

## Plugins that persist state

Who installs a plugin decides where its data lives (SQLite, Postgres, Supabase) and how it is reached (a direct connection or a claude.ai connector). Build for that instead of hard-coding one store.

1. Store: SQLite under `${CLAUDE_PLUGIN_DATA}` by default, so the plugin works with no setup. `sqlite_path` moves it; `database_url` (a `sensitive` `userConfig` option) connects to Postgres or Supabase directly. Say in the README that uninstalling the plugin from the last place it is installed deletes `${CLAUDE_PLUGIN_DATA}`, and a SQLite database inside it, unless `--keep-data` is passed. A database at `sqlite_path` outside that directory, or behind `database_url`, is not touched.
2. Route: a direct connection or a connector. Decide once, on first use, and have Claude save the result in `userConfig`. When the saved route is unavailable, stop and tell the user; never fall back to another store, or the data splits across two places. Find a connector by what it can do (runs SQL), not by tool name, because the server part of the name differs per user, and save its ID and any `project_id` it needs. Supabase's `execute_sql` takes only a query string, with no separate parameters.
3. Runner for a direct connection: an MCP server bundled with the plugin, limited to running SQL, applying migrations and the normalization functions. Claude Code substitutes a `sensitive` value into MCP and LSP server config and exec-form hook `args`, and exports it to hooks as `CLAUDE_PLUGIN_OPTION_<KEY>`, but skill content gets a placeholder and commands Claude runs through Bash get nothing. Of those, the MCP server's `env` is where this repo passes it.
4. SQL: Claude writes it. The plugin ships the schema and registration examples. Stick to SQL that runs on both SQLite and Postgres (`INSERT ... ON CONFLICT DO UPDATE`, `TEXT` / `INTEGER`, timestamps stored as text). Store JSON as `TEXT` with a `json_valid()` check in SQLite and as `jsonb` in Postgres: `->>` then reads it the same way on both, while a Postgres `text` column would need a cast first.
5. Rules that must hold on every write live in the schema (constraints, generated columns, triggers), so they hold whoever writes the SQL. Only a rule the schema can't express on both databases becomes a small function, such as NFKC normalization (SQLite has no `normalize()`). Don't call such a function from a SQLite generated column: other clients that lack the function (DB Browser and the like) can no longer read the table. Fill the column from a trigger instead.
6. Schema changes apply automatically and idempotently. Never ask the user to run an `ALTER` by hand. Over a connector, send DDL through the connector's migration tool (Supabase: `apply_migration`).
7. Extension points: every table has a stable primary key and an `updated_at` that the schema maintains (a default on insert, a trigger on update), because Claude's own `UPDATE` may leave it out. Trigger syntax differs between SQLite and Postgres, so the migrations ship one per database. Optional features such as vector search add no columns to the plugin's schema; whoever wants one adds their own column or table and a hook (for example `PostToolUse` matched to the tools that touch the database) and finds rows to refresh by comparing each row's `updated_at` with the value it recorded for that row when it last processed it. Don't keep a single `updated_at > cursor` watermark: writes that share a timestamp (SQLite's second-resolution `CURRENT_TIMESTAMP`, or every write in one Postgres transaction) slip past it.
