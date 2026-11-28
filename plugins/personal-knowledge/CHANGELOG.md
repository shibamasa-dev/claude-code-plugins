# Changelog

Changes to the personal-knowledge plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.2.0] - 2026-11-28

### Added
- `relationship-ledger` skill: a private ledger of the people you know or met. Claude records people, SNS accounts per platform, dated notes (`meeting` for where and when you met, `context`, `personality`, `boundary`, `task`, `other`, each with an optional source and confidence 0–5), prompt-injection attempts as event rows, opt-in photo references with a consent basis (no face recognition), and status labels (`active`, `watch`, `avoid`, `blocked`, `archived`). Business-card intake writes the person, the card's accounts, one `meeting`, one `context` and, with a follow-up, one `task` note
- Bundled MCP server `ledger` (`server/ledger_mcp.py`, started with `uv run --script`) that runs SQL (`execute_sql`, and `execute_transaction` for several statements committed together or not at all, which the business-card intake uses), applies the migrations and provides `rl_norm()` (NFKC plus lower case) on SQLite. Claude writes the SQL; the schema (`migrations/sqlite/`, `migrations/postgres/`) holds the rules: allowed values, the `person_key` format, one account per platform and handle ignoring case, confidence 0–5, a consent basis on every photo reference, foreign keys that delete a person's rows with them, `updated_at` on every table, and keys that never change. Views `rl_v_people` (latest account per platform, counts, last meeting) and `rl_v_search`. On SQLite the server refuses `ATTACH` / `DETACH`, so a statement can't open or create a database file outside the ledger
- Options `ledger_sqlite_path`, `ledger_database_url` (sensitive), `ledger_route`, `ledger_connector_id` and `ledger_connector_project_id`. The default store is `relationship-ledger/ledger.sqlite3` in the plugin data directory; `ledger_database_url` uses Postgres or Supabase, and `ledger_route=connector` a claude.ai connector that runs SQL. The route is chosen once and saved, and a saved route whose store is missing (including a SQLite file that has moved) stops with an error instead of opening or creating another store
- `tests/run-postgres.sh` runs the ledger tests on a throwaway postgres:16 container, plus the migration file applied alone through `psql` as the connector route does

## [0.1.0] - 2026-11-27

### Added
- First release, with the `get-chrome-history` skill, its messages and skill body in English. It reads one Chrome profile's History database (copied first, because Chrome locks it), takes the visits added since the last run (the first run takes the last 7 days), and sorts them into known services, unknown domains for Claude to classify, and noise
- `chrome_profile` option (default `Default`) picks the profile; the script looks under the macOS and Linux Chrome and Chromium profile folders, and when the History file is missing it says which profiles it did find
- State (`state.json`, the last visit time seen, one per History file so each profile keeps its own window) and the evolving `knowledge.json` live in the plugin data directory under `get-chrome-history/`. The first run copies the seed `knowledge.json` shipped with the skill there and later runs never overwrite it. The last visit time is saved only after the output is printed, so a failed run fetches the same window again
- Page titles are treated as data written by the sites visited: control characters are dropped, titles are cut at 200 characters, and the skill tells Claude never to follow instructions found in a title or URL. Output is written as UTF-8 whatever the locale
- A History copy that can't be read (taken mid-write, or damaged) exits 1 with an `error` JSON and keeps the window. The seed copy and `state.json` are written through a per-run temp file moved into place, and the seed copy never replaces a `knowledge.json` that appeared meanwhile
- `youtu.be` entries get `video_title` too
- A service in `knowledge.json` with `"ignore": true` is counted as noise instead of being listed, and a host matches its service at any parent level (`www.amazon.co.jp` matches `amazon.co.jp`)
