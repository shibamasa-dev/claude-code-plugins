# inventory

English | [日本語](README.ja.md)

An inventory database of the things you own: electronic parts, dev boards, tools, consumables and gadgets. Claude registers items from photos of the real thing, keeps what it couldn't read as `needs_review`, and finds them again with NFKC-normalized search. The data lives in SQLite by default, or in Postgres / Supabase, reached directly or through a claude.ai connector.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install inventory@shibamasa-plugins
```

With no settings, it works right away with a SQLite file in the plugin's data directory.

## Skills

| Skill | Use it for |
|---|---|
| `inventory` | "Do I have a 10k resistor?", "Where is the soldering iron?", or photos of parts to catalogue. Claude searches with `norm()`, registers with an upsert that only touches the columns it read, writes unreadable columns to `needs_review` instead of guessing, keeps a label's pack size (`attrs.pack_qty`) apart from the count in hand (`qty`), and won't state a quantity that hasn't been counted |

## MCP server

`server/inventory_mcp.py`, declared in `.mcp.json` as `db` and started with `uv run --script`. It only does three things:

| Tool | What it does |
|---|---|
| `execute_sql` | Runs one SQL statement that Claude wrote and returns the rows as JSON (at most 500) |
| `apply_migrations` | Applies pending migrations (they also run on the first tool call) and reports the backend, the SQLite file and the schema versions |

On SQLite it also registers `norm(text)` (NFKC, then lower case) on every connection; on Postgres the migration creates the same function. The server opens the database on the first tool call, not at startup, with a 10-second connect timeout, and replaces a Postgres connection that has dropped. A statement that was running when the connection dropped is not run again (it may already be committed); that call fails and says so. It never switches stores: if `database_url` doesn't connect, every call fails with the error.

## Schema

`migrations/sqlite/` and `migrations/postgres/` hold the same schema in each dialect, applied in name order and recorded in `inv_schema_migrations`. Every file is safe to apply twice.

| Object | What it is |
|---|---|
| `inv_items` | One row per item. Primary key `item_key` (a slug that can't change). `qty` is NULL when not counted and 0 when none are left. `needs_review` lists unconfirmed columns (`qty,attrs.remaining`). `location` is where it is kept, `photo_ref` points to the photo |
| `inv_categories` | `code`, `name`, `kind` (`part`, `consumable`, `tool`, `device`). 27 seeded; add your own with `INSERT` |
| `inv_v_items`, `inv_v_needs_review` | The search entry point, and the rows that need a look at the real thing |

Rules that must hold on every write are in the schema: `CHECK` constraints and a foreign key to the categories, and three triggers on `inv_items` (refresh `search_text`, set `updated_at` on every update, reject a changed `item_key`). Timestamps are UTC text with milliseconds (`2026-10-11T09:30:00.123Z`) on both databases. On Postgres, row level security is enabled with no policies, and the views are revoked from the Supabase API roles `anon` and `authenticated` when those roles exist.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `sqlite_path` | empty (`inventory.sqlite3` in the data directory) | Where the SQLite file is. `~` is expanded; a relative path is relative to the data directory |
| `database_url` | empty | `postgresql://...` for Postgres or Supabase. When set, the server connects there instead of SQLite. `sensitive`: kept in secure storage, not in `settings.json` |
| `photo_dir` | empty (`photos/` in the data directory) | Where Claude copies photos on this machine. `photo_ref` is relative to it |
| `route` | empty | `direct` (the bundled server) or `connector`. Claude decides on first use and saves it |
| `connector_id` | empty | With `connector`: the server part of the connector's tool names. Saved by Claude |
| `connector_project_id` | empty | With `connector`: the `project_id` its SQL tool needs (Supabase). Saved by Claude |

Claude saves the route with `claude plugin configure inventory@shibamasa-plugins --values-stdin`. Set `database_url` yourself in `/plugin` (or with that command), then run `/reload-plugins`.

### Routes

- **Direct**: the bundled MCP server, against SQLite or `database_url`
- **Connector**: a claude.ai connector that runs SQL against your Postgres, such as the Supabase connector (`execute_sql(project_id, query)` takes only a SQL string, so Claude embeds values as literals). Schema changes go through its migration tool (`apply_migration`) with the files in `migrations/postgres/`. Claude finds the connector by what it can do, not by its name

When the saved route stops working, Claude stops and tells you. It never falls back to another store, so the data doesn't split across two places.

## Your data

The default SQLite file is inside the plugin data directory (`~/.claude/plugins/data/<plugin id>/`). **Uninstalling the plugin from the last scope it is installed in deletes that directory, and the database and photos in it**, unless you pass `--keep-data`:

```text
claude plugin uninstall inventory@shibamasa-plugins --keep-data
```

A file at a `sqlite_path` outside that directory, a `photo_dir` outside it, and a database behind `database_url` or a connector are never touched.

## Extending

Optional features such as vector search add no columns to the plugin's schema. Add your own column or table (for example `my_item_embeddings (item_key, embedded_updated_at, embedding)`) and a hook, such as a `PostToolUse` hook matched to `mcp__plugin_inventory_db__execute_sql`, that refreshes it.

To find the rows to refresh, compare each row's `updated_at` with the `updated_at` you recorded for that row when you last processed it (`WHERE e.item_key IS NULL OR e.embedded_updated_at <> i.updated_at`). Don't keep one cursor time for the whole table (`updated_at > :last_run`): writes that share the same timestamp get skipped.

## Limitations

- On SQLite, the triggers call `norm()`, which only the bundled server provides. Other clients (the `sqlite3` shell, DB Browser) can read every table, but their writes to `inv_items` fail with `no such function: norm`
- `attrs ->> 'key'` needs SQLite 3.38 or later
- The Postgres migration creates `norm(text)` and the `inv_` objects in the first schema on `search_path` (`public` on Supabase) and replaces a function already named `norm(text)` there
- One SQL statement per `execute_sql` call. No bind parameters, the same as a connector

## Requirements

- [`uv`](https://docs.astral.sh/uv/) to start the MCP server (it installs Python and `psycopg` on first run)
- For the connector route, a claude.ai connector that runs SQL and applies migrations

## Tests

```bash
bash plugins/inventory/tests/run-all.sh        # SQLite, plain python3 (what CI runs)
bash plugins/inventory/tests/run-postgres.sh   # the same tests on postgres:16 in Docker, plus the migration file run with psql alone
```

Each test talks to the server over stdio the way Claude Code does (`tests/mcp_call.py`). The fixtures are rows from a real inventory, trimmed of anything personal.
