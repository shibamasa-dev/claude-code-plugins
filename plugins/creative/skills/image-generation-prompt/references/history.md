# Image history: routes, SQL and reference proxies

The schema is in the plugin's `migrations/` folder (one folder per database; SKILL.md gives its path). Those files are the reference for columns and allowed values. Claude writes the SQL; the schema enforces the rules (allowed `status` and `role` values, `output_paths` as a JSON array, `updated_at`, `search_text`, ids that never change), so stick to the forms below and let the schema do the rest.

## 1. Pick the route (before the first query in a session)

The saved settings (`route`, `connector_id`, `connector_project_id`) are printed in SKILL.md's Image history section.

- **`sqlite`** or **`postgres`**: this plugin's MCP server, the tools `execute_sql` and `apply_migrations` of the server `history` (`mcp__plugin_creative_history__execute_sql`), against the SQLite file or `database_url`. The server checks the saved store against the settings: with `postgres` and no `database_url` (or `sqlite` with one) every call fails, and that error means stop and tell the user.
- **`connector`**: the saved connector's SQL tool (for Supabase, `execute_sql` with `project_id` = the saved project). Before the first query in a session, bring the schema up to date (section 2).
- **Empty**: decide once, then save.
  1. If the user said the history should live in a database they reach through a claude.ai connector, or this plugin's MCP tools aren't available here, look for a connector **by what it can do, not by its name**: a tool that runs a SQL string against Postgres, and one that applies a migration. Supabase's are `execute_sql(project_id, query)` and `apply_migration(project_id, name, query)`. Ask which connector and project to use if there is more than one, then save `route=connector`, `connector_id` (the `<server>` in `mcp__<server>__<tool>`) and `connector_project_id`.
  2. Otherwise call `apply_migrations` on this plugin's server. If it answers, save its `backend` (`sqlite` or `postgres`) as `route`. Its `database` field says where the data is; tell the user once.
  3. If neither works, stop and tell the user what is missing. Don't keep the history somewhere else.
- Save with `echo '{"route":"sqlite"}' | claude plugin configure <plugin id> --values-stdin` (the plugin id is the one from `claude plugin list`). Options you leave out keep their values.

**When the saved route doesn't work**, stop and tell the user. Never fall back to another store: the history would split across two places. Change the route only when the user asks to move the data.

If a call fails because the connection dropped while the statement ran, the statement may or may not have been applied. Check with a `SELECT` before running it again.

`database_url` is a secret. The user sets it in the plugin's settings (`/plugin`, or `claude plugin configure`) and then runs `/reload-plugins`. Don't ask for it in chat and don't write it anywhere.

## 2. Schema changes

- **`sqlite`, `postgres`**: the server applies new migrations by itself on its first tool call in a session. Never run `ALTER` or other DDL by hand.
- **connector**: run `SELECT version FROM img_schema_migrations` (an error saying the table doesn't exist means nothing is applied). For each file in the plugin's `migrations/postgres/` whose name (without `.sql`) isn't listed, in name order, send the whole file through the connector's migration tool, with the file name without `.sql` as the migration name. The files are safe to apply twice.

## 3. Search before planning

```sql
SELECT id, created_at, status, title, asset_type, style, composition, route, reuse_scope, based_on, tags,
       output_paths, reference_roles
  FROM img_v_attempts
 WHERE search_text LIKE '%' || img_norm('<term>') || '%' ESCAPE '\'
 ORDER BY created_at DESC
 LIMIT 5;
```

- `search_text` is NFKC-normalized and lower-cased by a trigger, so the term goes through the same `img_norm()`.
- Embed the term as a string literal: double every `'`, and put `\` before every `%`, `_` and `\` (and their full-width forms `％` `＿` `＼`, which NFKC turns into the plain ones). No bind parameters: a connector takes only a SQL string.
- One term per query, or several joined with `OR`. Try the words the user used and their likely translations (`バナー` / `banner`, `構図` / `composition`): NFKC folds width and case, not language.
- Only attempts with a reference of a given role: add `AND reference_roles LIKE '%style_only%'`.
- The references of one attempt: `SELECT * FROM img_references WHERE attempt_id = <id> ORDER BY id`.

## 4. Record an attempt

After every generation, and for a plan when generation is blocked or deferred:

```sql
INSERT INTO img_attempts (title, request, asset_type, style, composition, prompt, route, output_paths, based_on,
                          reuse_scope, tags, notes, status)
VALUES ('Mecha raid announcement banner', 'こんな感じの構図の画像作れる？ …', '16:9 anime game update banner',
        'high-energy anime sci-fi promotional art', 'left portrait cut-in, right giant mecha, bottom event title',
        '<the five-section prompt>', 'codex', '["/abs/path/out.png"]', NULL,
        'composition_only', '16:9,banner,anime,mecha,left-cutin,bottom-title', 'Original IP-safe version of the reference.',
        'generated')
RETURNING id;
```

- `request` is the user's request in their own words. `output_paths` is a JSON array of absolute paths (`'[]'` for a plan).
- `route` is the route id that generated it, or `NULL` for a plan only. `status`: `planned`, `generated`, `accepted`, `rejected`, `failed` or `superseded`.
- A refinement of an earlier attempt is a **new row** with `based_on` = that attempt's id. Don't overwrite the earlier row; mark it `superseded` if the new one replaces it.
- When the user accepts or rejects a result: `UPDATE img_attempts SET status = 'accepted', notes = coalesce(notes || ' ', '') || '<feedback>' WHERE id = <id>;` (the schema moves `updated_at`).

## 5. Reference proxies

A reference image worth reusing is kept as a compact proxy, never as a full-size copy and never inside the plugin. Make it with the `history.py proxy` command in SKILL.md's Image history section (run it exactly as written there, so it gets the right data directory). It writes a JPEG (longer edge at most 1280 px, never enlarged, metadata stripped) to `image-history/references/` in the plugin data directory and prints the values to record. Pass `--no-proxy` for a reference kept as notes only (rejected, low-value, or legally risky): it hashes and measures the source and writes nothing. Then:

```sql
INSERT INTO img_references (attempt_id, role, label, source_path, source_sha256, source_bytes, proxy_ref, proxy_bytes,
                            width, height, max_edge, format, notes)
VALUES (<attempt id>, 'style_only', 'mecha banner style', '<source_path>', '<source_sha256>', <source_bytes>,
        '<proxy_ref>', <proxy_bytes>, <width>, <height>, 1280, 'jpg', NULL)
ON CONFLICT (attempt_id, source_sha256) DO UPDATE SET role = excluded.role, label = excluded.label, notes = excluded.notes;
```

To look at a stored proxy, open `image-history/references/<proxy_ref>` in the plugin data directory (the command prints its full path as `proxy_path`). On the connector route the proxies still live on this machine; only the rows are in the remote database.

### Reference roles

Every reference has a role saying what a later generation may borrow from it:

| Role | May borrow |
|---|---|
| `composition_only` | layout, framing, subject placement, reading order, camera angle |
| `style_only` | line quality, rendering, shading, texture, glow, finish, detail density, color grading |
| `palette_only` | color mood, contrast, grading, accent colors |
| `typography_only` | title treatment, outline or glow, hierarchy, text density (not the words or logos) |
| `subject_only` | the broad class of subject or motif, not an exact character or object design |
| `full_reference` | broad inspiration across several of the above; still no copying of protected specifics |
| `none` | provenance only; not for reuse |

When the user says "only the taste", "only the art style" or 「テイストだけ」「画風だけ」「雰囲気だけ」, use `style_only`, and say in the prompt what to avoid: composition, pose, character identity, object design, logos, exact text, costume and layout.

## What not to store

No secrets, and nothing about the user that isn't about this image work. A single liked result is not a general preference unless the user says so.
