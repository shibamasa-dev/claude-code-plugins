# Changelog

Changes to the inventory plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.1] - 2026-11-21

### Changed
- The inventory skill quotes its Japanese spelling examples in backticks, so editing that line passes the repo's language check (#112).

## [0.1.0] - 2026-10-11

### Added
- First release: the `inventory` skill, a bundled stdio MCP server (`execute_sql`, `apply_migrations`, `norm()` on SQLite), and the schema for SQLite and Postgres (`inv_items`, `inv_categories`, `inv_schema_migrations`, two views, three triggers on `inv_items`)
- Stores in SQLite by default, in Postgres or Supabase with `database_url`, or through a claude.ai connector that runs SQL
- Skill bodies, messages and tests are in English
