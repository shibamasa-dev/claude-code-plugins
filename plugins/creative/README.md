# creative

English | [日本語](README.ja.md)

Skills for making images and videos.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install creative@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `image-generation-prompt` | Proposes image assets when they would improve a page, deck or document, generates only after you approve, and structures the prompt for the route you configured (Codex, Gemini API, OpenAI Image API, fal.ai). Searches the image history before planning and records every attempt, with reference images kept as compact proxies |
| `motion-video` | Draws motion-graphics videos in code and renders them, with your product images, screenshots, logos or live-action clips |

`DESIGN.md` linting moved to the `lint` plugin. To keep it, run `/plugin install lint@shibamasa-plugins`.

## MCP server

`server/history_mcp.py`, declared in `.mcp.json` as `history` and started with `uv run --script`. It only runs SQL for the image history:

| Tool | What it does |
|---|---|
| `execute_sql` | Runs one SQL statement that Claude wrote and returns the rows as JSON (at most 500) |
| `apply_migrations` | Applies pending migrations (they also run on the first tool call) and reports the backend, the SQLite file and the schema versions |

On SQLite it also registers `img_norm(text)` (NFKC, then lower case) on every connection; on Postgres the migration creates the same function. The server opens the database on the first tool call, not at startup. It never switches stores: if `database_url` doesn't connect, every call fails with the error.

## Schema

`migrations/sqlite/` and `migrations/postgres/` hold the same schema in each dialect, applied in name order and recorded in `img_schema_migrations`. Every file is safe to apply twice.

| Object | What it is |
|---|---|
| `img_attempts` | One row per image attempt (a plan, a generated image, a rejected draft, a variant). `based_on` links a refinement to the attempt it builds on; `route` is the route that generated it; `status` is `planned`, `generated`, `accepted`, `rejected`, `failed` or `superseded` |
| `img_references` | Reference images attached to an attempt, each with a `role` (`composition_only`, `style_only`, `palette_only`, `typography_only`, `subject_only`, `full_reference`, `none`), the source's hash and size, and the proxy file name |
| `img_v_attempts` | The search entry point: attempts with the roles of their references |

Rules that must hold on every write are in the schema: `CHECK` constraints, foreign keys, triggers that refresh `search_text`, set `updated_at` on every update and reject a changed `id`. Timestamps are UTC text with milliseconds on both databases. On Postgres, row level security is enabled with no policies, and the view is revoked from the Supabase API roles `anon` and `authenticated` when those roles exist.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `image_routes` | empty | Route ids to try for images, comma-separated, first one first: `codex`, `gemini`, `openai`, `fal` (for example `codex,gemini`). Empty means Claude asks you, and offers to save your answer |
| `video_routes` | empty | Route ids to try for video, the same way: `gemini`, `fal` |
| `sqlite_path` | empty (`image-history/history.sqlite3` in the data directory) | Where the image history's SQLite file is. `~` is expanded; a relative path is relative to the data directory |
| `database_url` | empty | `postgresql://...` for Postgres or Supabase. When set, the history server connects there instead of SQLite. `sensitive`: kept in secure storage, not in `settings.json` |
| `route` | empty | Where the image history lives: `sqlite` or `postgres` (through the bundled server) or `connector`. Claude decides on first use and saves it. Not related to `image_routes` |
| `connector_id` | empty | With `connector`: the server part of the connector's tool names. Saved by Claude |
| `connector_project_id` | empty | With `connector`: the `project_id` its SQL tool needs (Supabase). Saved by Claude |

Set them in `/plugin`, or with `echo '{"image_routes":"codex,gemini"}' | claude plugin configure creative@shibamasa-plugins --values-stdin`, then run `/reload-plugins`. How each route is called is in `skills/image-generation-prompt/references/routes.md`. Set `database_url` yourself; Claude saves `route` and the connector keys.

### Image history routes

- **`sqlite`**: the bundled MCP server, against the SQLite file
- **`postgres`**: the bundled MCP server, against `database_url`. If `database_url` is later empty, the server stops instead of opening SQLite; if `route` is `sqlite` and `database_url` is set, it stops until the two agree
- **`connector`**: a claude.ai connector that runs SQL against your Postgres, such as the Supabase connector. Schema changes go through its migration tool with the files in `migrations/postgres/`. Claude finds the connector by what it can do, not by its name

When the saved route stops working, Claude stops and tells you. It never falls back to another store, so the history doesn't split across two places. Reference proxies stay on this machine on either route.

### Where files go

| What | Where |
|---|---|
| A motion-video project (`brief.md`, `music-brief.md`, `verify.md`, `video.js`, `out/`) | the folder you name, else `motion-video/<slug>/` under the working directory |
| motion-video's working PNG sequence and audio files | `os.tmpdir()/motion-video/`, not removed automatically; delete it when the video is done |
| Generated images | the deliverable's own folder (for example `assets/`), with an absolute save path given to the route |
| The image history database | `image-history/history.sqlite3` in the plugin data directory, unless `sqlite_path` or `database_url` moves it |
| Reference image proxies (JPEG, longer edge at most 1280 px) | `image-history/references/` in the plugin data directory |
| The soundfont for BGM | `~/.local/share/motion-video/soundfonts/`, where you put it |
| Python packages uv downloads | uv's own cache (`uv cache dir`, usually `~/.cache/uv`). The SQLite history downloads none. The first start with `database_url` adds psycopg (about 24 MB, from PyPI), and the first proxy adds Pillow (about 28 MB). Uninstalling the plugin leaves them; `uv cache clean psycopg psycopg-binary pillow` removes them |

## Your data

The default image history and the reference proxies are in the plugin data directory (`~/.claude/plugins/data/<plugin id>/`). **Uninstalling the plugin from the last scope it is installed in deletes that directory, with the history and proxies in it**, unless you pass `--keep-data`:

```text
claude plugin uninstall creative@shibamasa-plugins --keep-data
```

A file at a `sqlite_path` outside that directory and a database behind `database_url` or a connector are never touched. The motion-video files and generated images above are outside it, so uninstalling removes none of them.

## Requirements

- `image-generation-prompt`: the route you use: the Codex CLI signed in (`codex`), or an API key in the environment (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `FAL_KEY`)
- The image history: [uv](https://docs.astral.sh/uv/) (it starts the MCP server, and on first use downloads Pillow for the proxies and, with `database_url`, psycopg). SQLite needs nothing else; Postgres 13 or later, or Supabase, for `database_url`. Without uv the `history` server doesn't start and the proxy command fails; image-generation-prompt still works, without the history
- `motion-video`: Node.js, Chrome, ffmpeg

## Tests

```bash
bash plugins/creative/tests/run-all.sh        # SQLite; needs uv for the proxy tests
bash plugins/creative/tests/run-postgres.sh   # the same against a throwaway postgres:16 container; needs docker, psql and uv
```
