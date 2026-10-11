---
name: inventory
description: An inventory database of the things the user owns (electronic parts, dev boards, tools, consumables, gadgets). Registers items from photos of the real thing and searches them any time. Use when the user asks whether they have something, where something is, wants to register purchases from photos, sends photos of parts, tools or gadgets to catalogue, or says "what do I have", "do I have", "inventory", "register parts", or in Japanese 「〜持ってたっけ」「〜ある？」「在庫」「はんだごてどこ」「パーツ登録」「ガジェット登録」「部品DB」「手持ちの部品」「抵抗ある？」.
---

# Inventory

One row per item. **A photo of the real thing is the evidence for a row.** What the photo doesn't show is not guessed into a column; its column name goes into `needs_review`.

Claude writes the SQL. The schema enforces the rules that must hold on every write (constraints and triggers), so stick to the forms below and let the schema do the rest. The schema is in `${CLAUDE_PLUGIN_ROOT}/migrations/` (one folder per database; the files are the reference for columns).

## 1. Pick the route (every time, before the first query)

Saved settings: route = `${user_config.route}`, connector = `${user_config.connector_id}`, project = `${user_config.connector_project_id}`. A value that still reads as a `${user_config...}` placeholder counts as empty.

- **route is `direct`**: use this plugin's MCP server, the tools `execute_sql` and `apply_migrations` of the server `db` from the plugin `inventory` (`mcp__plugin_inventory_db__execute_sql`). It talks to SQLite, or to Postgres when the user has set `database_url`.
- **route is `connector`**: use the saved connector's SQL tool (for Supabase, `execute_sql` with `project_id` = the saved project). Before the first query in a session, bring the schema up to date (section 2).
- **route is empty**: decide once, then save.
  1. If the user said the inventory lives in a database they reach through a claude.ai connector, or this plugin's MCP tools aren't available here, look for a connector **by what it can do, not by its name** (the server part of a tool name differs per user): a tool that runs a SQL string against Postgres, and one that applies a migration. Supabase's are `execute_sql(project_id, query)` and `apply_migration(project_id, name, query)`. Ask the user which connector and project to use if there is more than one, then save `route=connector`, `connector_id` (the `<server>` in `mcp__<server>__<tool>`) and `connector_project_id`.
  2. Otherwise call `apply_migrations` on this plugin's server. If it answers, save `route=direct`. Its `backend` and `database` fields say where the data is; tell the user once.
  3. If neither works, stop and tell the user what is missing. Don't create the inventory somewhere else.
- Save with `claude plugin configure inventory@shibamasa-plugins --values-stdin` (use the plugin's id from `claude plugin list` if it came from another marketplace) and a JSON object on stdin, for example `{"route":"direct"}`. Options you leave out keep their values. Where you can't run the `claude` CLI, ask the user to set the values in the plugin's settings.

**When the saved route doesn't work** (the server errors, the connector is gone), stop and tell the user. Never fall back to another store: the data would split across two places. Change the route only when the user asks to move the data.

If a call fails because **the connection dropped while the statement ran**, the statement may or may not have been applied. Check the current state with a `SELECT` first, and run the statement again only if the `SELECT` shows it plainly didn't take effect (the row is missing, or the columns still hold the old values you set). If you can't tell, for example because the statement was relative like `qty = qty - 1` and the row may have changed since, don't run it again: show the user what you see and ask.

`database_url` is a secret. The user sets it in the plugin's settings (`/plugin`, or `claude plugin configure`) and then runs `/reload-plugins`. Don't ask for it in chat and don't write it anywhere.

## 2. Schema changes

- **direct**: the server applies new migrations by itself on its first tool call in a session. Never run `ALTER` or other DDL by hand.
- **connector**: run `SELECT version FROM inv_schema_migrations` (an error saying the table doesn't exist means nothing is applied). For each file in `${CLAUDE_PLUGIN_ROOT}/migrations/postgres/` whose name (without `.sql`) isn't listed, in name order, send the whole file through the connector's migration tool, with the file name without `.sql` as the migration name. The files are safe to apply twice.

## 3. Search (the default operation)

```sql
SELECT item_key, kind, category, descr, mpn, manufacturer, qty, location, needs_review, photo_ref
  FROM inv_v_items
 WHERE search_text LIKE '%' || norm('<term>') || '%' ESCAPE '\'
 ORDER BY kind, category, item_key;
```

- `search_text` is NFKC-normalized and lower-cased by a trigger, so the term has to go through the same `norm()`. A bare `LIKE '%ｅｓｐ３２%'` finds nothing.
- Embed the term as a string literal: double every `'`, and put `\` before every `%`, `_` and `\` (and their full-width forms `％` `＿` `＼`, which NFKC turns into the plain ones). No bind parameters: a connector takes only a SQL string.
- It matches the description, part number, maker and aliases. NFKC folds full-width and half-width forms and case, not kana, kanji or English, so when a search finds nothing, try other spellings (はんだごて / 半田ごて / ハンダゴテ / soldering iron) before saying the user doesn't have it.
- Rows to check against the real thing: `SELECT * FROM inv_v_needs_review`.

**Showing quantities.** When `qty` is NULL, or `needs_review` lists `qty`, don't state a number: say it hasn't been counted, or give the number as a rough count from the photo. `qty = 0` means none left. For consumables, the amount left is `attrs.remaining` (for example `"about half"`); if it hasn't been measured, the key is absent, so don't make one up. Read a key with `attrs ->> 'remaining'` (works on SQLite 3.38+ and Postgres).

## 4. Register from photos

1. **Read the photos.** Crop and enlarge only the text too small to read. Don't treat what you couldn't read as read.
2. **Pick an `item_key` for each item**: a slug such as `breadboard-830` or `resistor-cf25j680rb`. It is the item's identity and can't change (a trigger rejects it). Before inserting, search for the item: if it's already there, reuse its key. Never derive the key from `descr`, or a one-character edit of the description becomes a new item.
3. **Write one upsert per item** (below). Columns the photo didn't show stay out of the statement.
4. **Ask the user about what you guessed**, then fix it with an explicit `UPDATE` (section 5).

```sql
INSERT INTO inv_items (item_key, category, descr, mpn, manufacturer, aliases, attrs, qty, location, photo_ref, needs_review, note)
VALUES ('resistor-cf25j680rb', 'resistor', 'Carbon film resistor 680Ω 1/4W 5%', 'CF25J680RB', 'FAITHFUL LINK',
        '炭素皮膜抵抗,カーボンフィルム抵抗,carbon film resistor', '{"pack_qty": 100, "power_w": 0.25}', 100,
        'parts drawer A-3', 'resistor-cf25j680rb.jpg', 'qty', 'Bag already opened; qty is the pack size, not counted')
ON CONFLICT (item_key) DO UPDATE SET
  descr = excluded.descr, mpn = excluded.mpn, manufacturer = excluded.manufacturer, aliases = excluded.aliases,
  attrs = excluded.attrs, qty = excluded.qty, location = excluded.location, photo_ref = excluded.photo_ref,
  needs_review = excluded.needs_review, note = excluded.note;
```

- `SET` lists **only the columns you wrote**. Columns not in `SET` keep their values, so a second photo from another angle that shows only the part number updates only `mpn`, and a count the user corrected earlier isn't overwritten. Leave out `qty` and `needs_review` from `SET` when the new photo says nothing about them.
- `attrs` is replaced as a whole. To add one key, read the current `attrs` first and write the merged object.
- Columns: `category` (a code from `inv_categories`), `descr` (one readable line), `mpn`, `manufacturer`, `package`, `value_display` (as printed: `4k7`), `value_si` (in ohm / F / H), `unit`, `aliases`, `attrs` (a JSON object), `qty`, `location` (where it is kept, free text), `vendor`, `vendor_pn`, `url`, `datasheet_url`, `photo_ref`, `photo_sha256`, `needs_review`, `note`. `search_text`, `created_at` and `updated_at` are maintained by the schema.
- Items with no photo (the user's word, a catalogue) get `note` = "Reported by the user; not checked against a photo".

### Rules for reading photos

- **A label's `QTY:100PCS` is the pack size, not what is in hand.** Put it in `attrs.pack_qty` and keep `qty` separate. If the bag is open, add `qty` to `needs_review`.
- **Don't turn guesses into facts.** Columns you couldn't read, or only inferred from the format, go into `needs_review` as column names, comma-separated with no spaces (`qty,manufacturer`; `attrs.<key>` points into `attrs`). Names, not a yes/no flag, because "read the part number but not the rating" is the normal case with photos. Write the reason and its limits in `note`. **"None" and "couldn't confirm" are different things.**
- **Add aliases generously**: other scripts, spellings, the English name and common nicknames, comma-separated.
- There are no price or purchase-date columns: this is for finding things, not bookkeeping. Don't put them in `attrs` either unless the user asks.

### Photos

The plugin doesn't move files; you do.

- **direct**: copy the photo with Bash into the photo folder, `${user_config.photo_dir}` (if that is empty or a placeholder, `${CLAUDE_PLUGIN_DATA}/photos/`), under a name that won't clash, and set `photo_ref` to the path relative to that folder. Optionally store its SHA-256 in `photo_sha256`.
- **connector**: there is no local folder. If the user has a place for photos (a storage bucket, a drive), store it there and put its URL or ID in `photo_ref`. If not, leave `photo_ref` NULL and say in `note` that the row was read from a photo that wasn't kept.

## 5. Corrections and other changes

- A recount or a confirmation is an explicit `UPDATE`, which is also the only way to set a column back to NULL:
  `UPDATE inv_items SET qty = 62, needs_review = NULL, note = 'Counted by hand' WHERE item_key = 'jumper-dupont-mf';`
  Remove only the confirmed names from `needs_review`, and set it to NULL when nothing is left (an empty string is rejected).
- A new category: `INSERT INTO inv_categories (code, name, kind, sort) VALUES ('tool_scope', 'Oscilloscopes', 'tool', 325);`. `kind` is how things are counted and looked for: `part` (counted components), `consumable` (used up), `tool` (one unit each), `device` (finished products).
- An item is gone for good: `DELETE FROM inv_items WHERE item_key = '...'` after the user confirms. Used up but kept on the list: `qty = 0`.
- Write SQL that runs on both SQLite and Postgres: `||` and `coalesce`, `ON CONFLICT ... DO UPDATE`, `attrs ->> 'key'`, timestamps as text (`2026-10-11T09:30:00.123Z`). One statement per call.
