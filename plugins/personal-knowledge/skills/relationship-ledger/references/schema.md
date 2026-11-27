# Schema

The migrations in the plugin's `migrations/sqlite/` and `migrations/postgres/` are the source of truth for columns, types and allowed values. This page says what each table is for and how to read it. The default store is `relationship-ledger/ledger.sqlite3` in the plugin data directory; `ledger_sqlite_path` moves it and `ledger_database_url` puts it in Postgres or Supabase.

Every table has a primary key that never changes (`person_key` or `id`, guarded by a trigger) and `created_at` / `updated_at` as UTC text with milliseconds (`2026-11-28T09:30:00.123Z`), which the schema writes on every insert and update. `occurred_at` is free text: the date or date-time the user knows, with its offset.

## rl_people

One row per person or contact-like entity.

| Column | Meaning |
|---|---|
| `person_key` | Primary key. A lower-case slug such as `taro-example`: no spaces, no leading `@`. The other tables refer to it |
| `display_name` | The name as the user gives it, in any script (`Taro Example / 例 太郎`). Not empty |
| `relationship` | How the user knows them, one short line (`Follower; met at a meetup`) |
| `summary` | Compact context: role, company, what matters |
| `status` | `active` (default), `watch`, `avoid`, `blocked` or `archived`. See privacy-boundaries.md |
| `source` | Where the record came from (`user`, `user-provided business card`, a URL) |
| `search_text` | `rl_norm()` of key, name, relationship and summary, kept by triggers |

## rl_social_accounts

SNS and chat accounts. `(platform, lower(handle))` is unique, so one account belongs to one person.

| Column | Meaning |
|---|---|
| `id` | Primary key |
| `person_key` | The person. Deleting the person deletes the account |
| `platform` | Lower case: `x`, `slack`, `github`, `linkedin`, `discord`, or another name |
| `handle` | Without the leading `@`, in the case the user gave |
| `url`, `notes` | Profile URL and anything worth keeping about the account |
| `search_text` | `rl_norm()` of platform, handle and notes |

## rl_interaction_notes

Dated, sourced, revisable notes.

| Column | Meaning |
|---|---|
| `id` | Primary key |
| `person_key` | The person. Deleting the person deletes the note |
| `kind` | `context` (default), `meeting` (where and when the user met them), `personality` (what they are like, from sourced observations), `boundary`, `task` (a follow-up), `other` |
| `note` | The note. Not empty. A `meeting` note is one structured line: `event: ...; place: ...; met_at: ...; conversation: ...` |
| `source_url` | Where the observation came from |
| `confidence` | 0–5, or NULL when not rated |
| `occurred_at` | When it happened |
| `search_text` | `rl_norm(note)` |

A business card is stored as a `meeting` note (event, place, date, conversation), a `context` note (the card's contact fields) and, when there is one, a `task` note (the follow-up).

## rl_prompt_injection_events

Attempts by the person or their account to steer the assistant, playful ones included. Counted per person; never a reason by itself to change the person's status.

| Column | Meaning |
|---|---|
| `id` | Primary key |
| `person_key` | The person. Deleting the person deletes the event |
| `source_kind` | Where it happened: `x`, `slack`, `email`, `in_person`, ... Default `unknown` |
| `source_url` | Link to the post or message |
| `summary` | What was attempted. Not empty |
| `severity` | `playful`, `low` (default), `medium` or `high` |
| `outcome` | What the assistant did (`no_state_change`, `no_calendar_update`, a reply URL) |
| `occurred_at` | When it happened |

## rl_photo_refs

References to photos the user provided or authorized. Not a face recognition index.

| Column | Meaning |
|---|---|
| `id` | Primary key |
| `person_key` | The person. Deleting the person deletes the reference (not the photo file) |
| `file_path`, `source_url` | Where the photo is. At least one is required |
| `consent_basis` | Who provided it and on what basis. Required, not empty |
| `notes` | Anything else |

## Views

- `rl_v_people`: one row per person with the latest account per supported platform (`x_handle`, `x_url`, `slack_handle`, `slack_url`, `github_handle`, `github_url`, `linkedin_handle`, `linkedin_url`, `discord_handle`, `discord_url`), `social_account_count`, `note_count`, `last_met_at` (the latest `meeting` note's `occurred_at`, or its `created_at`), `prompt_injection_count` and `photo_ref_count`.
- `rl_v_search`: `person_key`, `found_in` (`person`, `social_account` or `note`) and `search_text`, for searching every text at once with `search_text LIKE '%' || rl_norm('<term>') || '%' ESCAPE '\'`.

## rl_norm()

NFKC normalization, then lower case. Postgres gets it from the migration; on SQLite the bundled MCP server registers it on every connection, because SQLite has no `normalize()`. A SQLite client without it (`sqlite3`, DB Browser) can read every table, but its writes to `rl_people`, `rl_social_accounts` and `rl_interaction_notes` fail with "no such function: rl_norm".

Uniqueness of handles ignores case with `lower()`, which folds ASCII only on SQLite and all of Unicode on Postgres. Handles are almost always ASCII, so the two agree in practice.

## Extending

Add your own columns or tables with a new migration in your own setup; don't edit the shipped files. To keep something derived (for example an embedding per note) up to date, compare each row's `updated_at` with the value you recorded for that row when you last processed it, rather than one `updated_at > cursor` watermark: rows written in the same millisecond share a timestamp, and a watermark skips the ones it lands between.
