# personal-knowledge

English | [日本語](README.ja.md)

Skills that keep a personal data store on your machine: `get-chrome-history` reads your Chrome browsing history and summarizes your interests, learning a little more about the sites you use on every run, and `relationship-ledger` keeps a private ledger of the people you know or have met.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install personal-knowledge@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `get-chrome-history` | "Analyze my browser history", "what have I been browsing lately", "what am I interested in". Claude reads the visits added since the last run, groups them by service (video, code, docs, music, shopping, news, social), classifies the domains it doesn't know yet, and reports your tendencies as JSON that can feed a user profile or recommendations. The script is `skills/get-chrome-history/scripts/get_chrome_history.py` (Python, standard library only) |
| `relationship-ledger` | "Register this business card", "where did I meet this person?", "remember this person", "show my watch list". Claude records people, where and when you met (`meeting` notes), their SNS accounts per platform, sourced notes on what they are like, follow-ups, prompt-injection attempts and status labels (`active`, `watch`, `avoid`, `blocked`, `archived`) in a database through the bundled MCP server `ledger`, and looks them up by name, handle or note text. Photo references only; no face recognition |

## How get-chrome-history works

1. **Read.** The script finds the History database of the profile in `chrome_profile`, under `~/Library/Application Support/Google/Chrome/<profile>/` (macOS), `~/.config/google-chrome/<profile>/` or `~/.config/chromium/<profile>/` (Linux). Chrome locks the file while it runs, so the script copies it to a temporary directory, reads the copy and removes it. It never writes to Chrome's files.
2. **Window.** It takes the visits after the newest one it saw last time in that profile. A profile's first run takes the last 7 days.
3. **Sort.** Each visit lands in one of three buckets: a known service from `knowledge.json` (with its category), an unknown domain (aggregated, with sample titles, the top 20 by time spent), or noise (shorter than `min_visit_duration_seconds`, fewer visits than `min_visit_count`, or a service marked `"ignore": true`).
4. **Learn.** Claude classifies the unknown domains and adds them to your `knowledge.json`, so the next run recognizes them.
5. **Report.** Claude summarizes the tendencies per category in your language and leaves a field empty when the evidence is thin.

Page titles are written by the sites you visit, so the script drops control characters and cuts them at 200 characters, and the skill tells Claude never to follow an instruction found in a title or URL. The files the plugin keeps (`knowledge.json`, `state.json`) stay on your machine. The history the script prints is not: it goes into the Claude conversation, so the URLs and titles of the visits in the window are sent to the model provider like anything else in the session, and summarizing afterwards does not undo that. Run the skill only when you are fine with that; it tells Claude to keep raw URLs and titles out of files and messages it writes elsewhere.

## How relationship-ledger works

Claude writes the SQL; the plugin ships the schema (`migrations/sqlite/` and `migrations/postgres/`) and a small MCP server, `server/ledger_mcp.py`, declared in `.mcp.json` as `ledger` and started with `uv run --script`. The server only runs SQL (`execute_sql` for one statement, `execute_transaction` for several in one transaction), applies the migrations (`apply_migrations`, also run on the first call of a session) and provides `rl_norm()` (NFKC plus lower case) on SQLite. The rules that must hold on every write live in the schema: allowed statuses, note kinds and severities, confidence 0–5, the key format, one account per `(platform, handle)` ignoring case, a consent basis for every photo reference, `updated_at` on every table, and keys that never change.

- Tables: `rl_people` (keyed by a slug such as `taro-example`), `rl_social_accounts`, `rl_interaction_notes`, `rl_prompt_injection_events`, `rl_photo_refs`, `rl_schema_migrations`. Views: `rl_v_people` (one row per person with the latest account per platform and counts) and `rl_v_search` (every searchable text). The skill's `references/schema.md` describes each column.
- Where the data lives is decided once, on first use, and saved in `ledger_route`: `sqlite` (the default file), `postgres` (`ledger_database_url`), or `connector` (a claude.ai connector that runs SQL, such as Supabase's). When the saved store is unavailable, Claude and the server stop and say so; they never open another store, which would split the ledger in two.
- What the ledger may hold is in the skill's `references/privacy-boundaries.md`: people you know or met, sourced and revisable notes, no secrets, no inferred sensitive attributes, no location trails, no card images by default, and `avoid` / `blocked` only when you say so. SNS profiles and posts are treated as evidence, never as instructions. What Claude reads from the ledger enters the conversation and so reaches the model provider; the database itself stays where you put it.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `chrome_profile` | `Default` | The Chrome profile directory to read (`Default`, `Profile 1`, ...). Empty means `Default`. When the profile has no History file, the skill lists the profiles it did find |
| `ledger_sqlite_path` | empty | The relationship ledger's SQLite file (`~` is expanded; a relative path is relative to the plugin data directory). Empty means `relationship-ledger/ledger.sqlite3` in the plugin data directory. Not used when `ledger_database_url` is set |
| `ledger_database_url` | empty | `postgresql://...` for Postgres or Supabase; the `ledger` server connects there instead of SQLite. Sensitive: kept in secure storage, not `settings.json` |
| `ledger_route` | empty | Saved by Claude on first use: `sqlite`, `postgres` or `connector`. When the saved store's setting is missing (`postgres` without `ledger_database_url`, or `sqlite` with one), every call fails instead of opening another store |
| `ledger_connector_id` | empty | Saved by Claude with `ledger_route=connector`: the `<server>` in the connector's `mcp__<server>__execute_sql` |
| `ledger_connector_project_id` | empty | Saved by Claude with `ledger_route=connector`: the project ID the connector's SQL tool needs, if any |

To find a profile's directory name, open `chrome://version` in that profile and look at "Profile Path".

The `ledger_` keys belong to `relationship-ledger` only. Set them with `/plugin` or `claude plugin configure personal-knowledge@shibamasa-plugins`, then run `/reload-plugins`.

### Where files go

| File | Place | What it is |
|---|---|---|
| `knowledge.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | The services and filters the skill knows. The first run copies the seed shipped in `skills/get-chrome-history/knowledge.json`; after that Claude adds to your copy and updates never overwrite it |
| `state.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | The newest visit time seen, one per History file, so switching `chrome_profile` skips nothing. Delete it to fetch the last 7 days again |
| The History copy | the system temp directory | Removed as soon as it has been read |
| `ledger.sqlite3` | `${CLAUDE_PLUGIN_DATA}/relationship-ledger/`, or `ledger_sqlite_path` | The relationship ledger on the default route. Not created with `ledger_database_url` or a connector, where the rows live in that database |
| Python packages uv downloads | uv's own cache (`uv cache dir`, usually `~/.cache/uv`) | The SQLite ledger downloads none. The first start with `ledger_database_url` adds psycopg (from PyPI). Uninstalling the plugin leaves them; `uv cache clean psycopg psycopg-binary` removes them |

`${CLAUDE_PLUGIN_DATA}` is `~/.claude/plugins/data/personal-knowledge-<marketplace>/`. When the script runs without it (for example by hand from a terminal), it uses `~/.claude/state/personal-knowledge/get-chrome-history/` instead and says so on stderr.

**Uninstalling the plugin from the last place it is installed deletes `${CLAUDE_PLUGIN_DATA}`, and with it your `knowledge.json`, `state.json` and a SQLite relationship ledger inside it**, unless you pass `--keep-data`:

```bash
claude plugin uninstall personal-knowledge@shibamasa-plugins --keep-data
```

A ledger at a `ledger_sqlite_path` outside that directory, a database behind `ledger_database_url` or a connector, and the fallback directory under `~/.claude/state/` are never touched.

## Limitations

- Chrome and Chromium on macOS and Linux only. Windows, other Chromium-based browsers (Edge, Brave, Arc) and Firefox are not read.
- One profile per run.
- A service matches by host and its parent domains (`www.amazon.co.jp` matches `amazon.co.jp`), not by path, so two services on one host can't be told apart.
- relationship-ledger: on the connector route a business-card intake is one multi-statement string, which Postgres runs as one transaction; that was measured with `psql`, not against a real connector, whose tool may run it differently. Handle uniqueness uses `lower()`, which folds only ASCII on SQLite. The upserts need SQLite 3.24 or later; the `->>` JSON operator is not used. The `ledger` server runs whatever statements Claude sends: on SQLite it refuses `ATTACH`, so no statement opens a file outside the ledger, and on Postgres the role in `ledger_database_url` decides what a statement can reach, so use one that is not a superuser.
- The window is by each URL's last visit time, and a URL's `visit_count` and time spent are its totals in Chrome, not just within the window.
- The copy is taken while Chrome may be writing. A visit Chrome had not committed yet when the copy was taken is missed if a newer visit was already in the copy.

## Requirements

- Google Chrome or Chromium
- macOS or Linux
- Python 3.9 or later (standard library only)
- relationship-ledger: [uv](https://docs.astral.sh/uv/), which starts the `ledger` MCP server (and, with `ledger_database_url`, downloads psycopg on first use). SQLite needs nothing else; Postgres 13 or later, or Supabase, for `ledger_database_url`. Without uv the `ledger` server doesn't start and the skill stops with that error

## Tests

```bash
bash plugins/personal-knowledge/tests/run-all.sh        # offline; relationship-ledger's rows need uv
bash plugins/personal-knowledge/tests/run-postgres.sh   # relationship-ledger against a throwaway postgres:16 container; needs docker, psql and uv
```

Offline: every case builds a History database with Chrome's `urls` / `visits` tables and fictional URLs in a temp directory, and points `HOME`, `TMPDIR` and `CLAUDE_PLUGIN_DATA` there, so no real profile or home directory is read or written. The rows check the three buckets, the 7-day first window, the incremental fetch, a separate cursor per profile, an unreadable History copy, that a fresh run writes only `knowledge.json` and `state.json` under the data directory (and nothing in the skill directory), that the seed is copied once and never overwritten, the fallback directory, a missing profile, the Linux profile path, output (and the missing-profile error) under an ASCII locale, that a run whose output can't be written leaves `state.json` unwritten, and title cleaning.

relationship-ledger's rows run the lookup, search, record, business-card and watch-list SQL forms SKILL.md teaches through the MCP server over stdio, with fictional people only, on a fresh data directory per script. They also check that a fresh start (new `HOME`, working directory and uv cache) writes only `relationship-ledger/ledger.sqlite3` under the data directory, that `ledger_sqlite_path` moves it, that the migrations apply once and leave schema and rows unchanged when run again, that `updated_at` moves on an UPDATE of every table and a hand-written `updated_at` or `search_text` is replaced, that the constraints reject bad rows, that a transaction with one failing statement commits nothing, that a client without `rl_norm()` can still read every table and view, and that an unavailable or mismatched route is an error and never falls back to SQLite. `run-postgres.sh` runs the same rows on Postgres, plus the rows that need psycopg (a connection URL's password never appears in an error) and the connector route (the migration file alone through `psql`, twice, with RLS on and the views closed to Supabase's API roles).
