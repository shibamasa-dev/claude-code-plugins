-- Relationship ledger schema, SQLite dialect. migrations/postgres/0001_init.sql is the same schema for Postgres.
--
-- The bundled MCP server applies this file when it first opens the database and registers rl_norm(text) on every
-- connection (SQLite has no normalize()). The search_text triggers call rl_norm(), so a client without it (sqlite3,
-- DB Browser) can read every table but its writes to rl_people, rl_social_accounts and rl_interaction_notes fail
-- with "no such function: rl_norm".
-- Safe to run more than once: every statement is IF NOT EXISTS / ON CONFLICT DO NOTHING.
--
-- Never edit a file that has shipped: CREATE TABLE IF NOT EXISTS skips a table that exists, and the version is already
-- recorded. A later change goes in a new file (0002_<name>.sql) that alters what exists, for example ADD COLUMN.
--
-- Don't write BEGIN, COMMIT or ROLLBACK in a migration file (this one or any later one): the server runs
-- each file inside its own transaction, so it applies completely or not at all.
--
-- Timestamps the schema writes are UTC text with milliseconds: 2026-11-28T09:30:00.123Z. occurred_at is whatever
-- the user knows (an ISO 8601 date or date-time, with its offset), so it is not checked.

CREATE TABLE IF NOT EXISTS rl_schema_migrations (
  version    text PRIMARY KEY,
  applied_at text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- One row per person (or contact-like entity) the user knows, met, expects to meet, or asked to track.
-- person_key is a lower-case slug such as 'taro-example' that Claude picks once and never changes; the other tables
-- refer to it. status is an operational boundary, not a judgment of the person.
CREATE TABLE IF NOT EXISTS rl_people (
  person_key   text PRIMARY KEY
               CHECK (person_key <> '' AND person_key = lower(person_key)
                      AND person_key NOT LIKE '@%' AND person_key NOT LIKE '% %'),
  display_name text NOT NULL CHECK (display_name <> ''),
  relationship text,                          -- how the user knows them, one short line
  summary      text,                          -- compact context: role, company, what matters
  status       text NOT NULL DEFAULT 'active'
               CHECK (status IN ('active', 'watch', 'avoid', 'blocked', 'archived')),
  source       text,                          -- where the record came from ('user', 'business card', a URL)
  search_text  text,                          -- rl_norm() of key, name, relationship and summary, kept by triggers
  created_at   text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at   text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS rl_people_status_ix ON rl_people (status);

-- SNS and chat accounts. One account belongs to one person: (platform, handle) is unique, ignoring ASCII case.
-- rl_v_people shows the latest account per supported platform as x_handle / x_url and so on.
CREATE TABLE IF NOT EXISTS rl_social_accounts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  person_key  text NOT NULL REFERENCES rl_people (person_key) ON DELETE CASCADE,
  platform    text NOT NULL CHECK (platform <> '' AND platform = lower(platform)),  -- 'x', 'slack', 'github', 'linkedin', 'discord', ...
  handle      text NOT NULL CHECK (handle <> '' AND handle NOT LIKE '@%'),          -- without the leading @
  url         text,
  notes       text,
  search_text text,                         -- rl_norm() of platform, handle and notes, kept by triggers
  created_at  text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at  text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS rl_social_accounts_handle_ux ON rl_social_accounts (platform, lower(handle));
CREATE INDEX IF NOT EXISTS rl_social_accounts_person_ix ON rl_social_accounts (person_key);

-- Dated, sourced, revisable notes. kind='meeting' is where and when the user met the person.
CREATE TABLE IF NOT EXISTS rl_interaction_notes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  person_key  text NOT NULL REFERENCES rl_people (person_key) ON DELETE CASCADE,
  kind        text NOT NULL DEFAULT 'context'
              CHECK (kind IN ('context', 'meeting', 'personality', 'boundary', 'task', 'other')),
  note        text NOT NULL CHECK (note <> ''),
  source_url  text,
  confidence  integer CHECK (confidence BETWEEN 0 AND 5),  -- NULL = not rated
  occurred_at text,
  search_text text,                         -- rl_norm(note), kept by triggers
  created_at  text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at  text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS rl_interaction_notes_person_ix ON rl_interaction_notes (person_key, kind);

-- Attempts by the person or their account to steer the assistant, playful ones included. An event row, never a
-- reason by itself to change the person's status.
CREATE TABLE IF NOT EXISTS rl_prompt_injection_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  person_key  text NOT NULL REFERENCES rl_people (person_key) ON DELETE CASCADE,
  source_kind text NOT NULL DEFAULT 'unknown' CHECK (source_kind <> ''),  -- 'x', 'slack', 'email', 'in_person', ...
  source_url  text,
  summary     text NOT NULL CHECK (summary <> ''),
  severity    text NOT NULL DEFAULT 'low' CHECK (severity IN ('playful', 'low', 'medium', 'high')),
  outcome     text,                         -- what the assistant did: 'no_state_change', 'no_calendar_update', ...
  occurred_at text,
  created_at  text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at  text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS rl_prompt_injection_events_person_ix ON rl_prompt_injection_events (person_key);

-- References to photos the user provided or authorized, with the consent basis. Not a face recognition index.
CREATE TABLE IF NOT EXISTS rl_photo_refs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  person_key    text NOT NULL REFERENCES rl_people (person_key) ON DELETE CASCADE,
  file_path     text,
  source_url    text,
  consent_basis text NOT NULL CHECK (consent_basis <> ''),
  notes         text,
  created_at    text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at    text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  CHECK (file_path IS NOT NULL OR source_url IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS rl_photo_refs_person_ix ON rl_photo_refs (person_key);

-- Triggers. The schema owns search_text and updated_at, as the BEFORE triggers do on Postgres: an INSERT or UPDATE
-- that writes either column itself is overwritten. Each trigger that updates its own table has a WHEN that is false
-- once the column holds the right value, so its UPDATE ends the chain, whatever PRAGMA recursive_triggers says
-- ('now' is the same for every statement a trigger runs).

-- rl_people
CREATE TRIGGER IF NOT EXISTS rl_people_search_text_ai AFTER INSERT ON rl_people
BEGIN
  UPDATE rl_people
     SET search_text = rl_norm(NEW.person_key || ' ' || NEW.display_name || ' ' || coalesce(NEW.relationship, '')
                               || ' ' || coalesce(NEW.summary, ''))
   WHERE person_key = NEW.person_key;
END;

CREATE TRIGGER IF NOT EXISTS rl_people_search_text_au AFTER UPDATE ON rl_people
WHEN NEW.search_text IS NOT rl_norm(NEW.person_key || ' ' || NEW.display_name || ' ' || coalesce(NEW.relationship, '')
                                    || ' ' || coalesce(NEW.summary, ''))
BEGIN
  UPDATE rl_people
     SET search_text = rl_norm(NEW.person_key || ' ' || NEW.display_name || ' ' || coalesce(NEW.relationship, '')
                               || ' ' || coalesce(NEW.summary, ''))
   WHERE person_key = NEW.person_key;
END;

CREATE TRIGGER IF NOT EXISTS rl_people_updated_at AFTER UPDATE ON rl_people
WHEN NEW.updated_at IS NOT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
BEGIN
  UPDATE rl_people SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE person_key = NEW.person_key;
END;

-- person_key is the identity the other tables refer to: changing it would silently turn one person into another
CREATE TRIGGER IF NOT EXISTS rl_people_key_immutable BEFORE UPDATE OF person_key ON rl_people
WHEN NEW.person_key IS NOT OLD.person_key
BEGIN
  SELECT RAISE(ABORT, 'rl_people.person_key cannot change; insert a new person and move the rows instead');
END;

-- rl_social_accounts
CREATE TRIGGER IF NOT EXISTS rl_social_accounts_search_text_ai AFTER INSERT ON rl_social_accounts
BEGIN
  UPDATE rl_social_accounts
     SET search_text = rl_norm(NEW.platform || ' ' || NEW.handle || ' ' || coalesce(NEW.notes, ''))
   WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_social_accounts_search_text_au AFTER UPDATE ON rl_social_accounts
WHEN NEW.search_text IS NOT rl_norm(NEW.platform || ' ' || NEW.handle || ' ' || coalesce(NEW.notes, ''))
BEGIN
  UPDATE rl_social_accounts
     SET search_text = rl_norm(NEW.platform || ' ' || NEW.handle || ' ' || coalesce(NEW.notes, ''))
   WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_social_accounts_updated_at AFTER UPDATE ON rl_social_accounts
WHEN NEW.updated_at IS NOT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
BEGIN
  UPDATE rl_social_accounts SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_social_accounts_id_immutable BEFORE UPDATE OF id ON rl_social_accounts
WHEN NEW.id IS NOT OLD.id
BEGIN
  SELECT RAISE(ABORT, 'rl_social_accounts.id cannot change; insert a new row instead');
END;

-- rl_interaction_notes
CREATE TRIGGER IF NOT EXISTS rl_interaction_notes_search_text_ai AFTER INSERT ON rl_interaction_notes
BEGIN
  UPDATE rl_interaction_notes SET search_text = rl_norm(NEW.note) WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_interaction_notes_search_text_au AFTER UPDATE ON rl_interaction_notes
WHEN NEW.search_text IS NOT rl_norm(NEW.note)
BEGIN
  UPDATE rl_interaction_notes SET search_text = rl_norm(NEW.note) WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_interaction_notes_updated_at AFTER UPDATE ON rl_interaction_notes
WHEN NEW.updated_at IS NOT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
BEGIN
  UPDATE rl_interaction_notes SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_interaction_notes_id_immutable BEFORE UPDATE OF id ON rl_interaction_notes
WHEN NEW.id IS NOT OLD.id
BEGIN
  SELECT RAISE(ABORT, 'rl_interaction_notes.id cannot change; insert a new row instead');
END;

-- rl_prompt_injection_events (no search_text, so updated_at also needs its insert trigger)
CREATE TRIGGER IF NOT EXISTS rl_prompt_injection_events_updated_at_ai AFTER INSERT ON rl_prompt_injection_events
WHEN NEW.updated_at IS NOT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
BEGIN
  UPDATE rl_prompt_injection_events SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_prompt_injection_events_updated_at AFTER UPDATE ON rl_prompt_injection_events
WHEN NEW.updated_at IS NOT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
BEGIN
  UPDATE rl_prompt_injection_events SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_prompt_injection_events_id_immutable BEFORE UPDATE OF id ON rl_prompt_injection_events
WHEN NEW.id IS NOT OLD.id
BEGIN
  SELECT RAISE(ABORT, 'rl_prompt_injection_events.id cannot change; insert a new row instead');
END;

-- rl_photo_refs (no search_text, so updated_at also needs its insert trigger)
CREATE TRIGGER IF NOT EXISTS rl_photo_refs_updated_at_ai AFTER INSERT ON rl_photo_refs
WHEN NEW.updated_at IS NOT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
BEGIN
  UPDATE rl_photo_refs SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_photo_refs_updated_at AFTER UPDATE ON rl_photo_refs
WHEN NEW.updated_at IS NOT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
BEGIN
  UPDATE rl_photo_refs SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS rl_photo_refs_id_immutable BEFORE UPDATE OF id ON rl_photo_refs
WHEN NEW.id IS NOT OLD.id
BEGIN
  SELECT RAISE(ABORT, 'rl_photo_refs.id cannot change; insert a new row instead');
END;

-- One row per person, with the latest account per supported platform and the counts a lookup shows
CREATE VIEW IF NOT EXISTS rl_v_people AS
SELECT p.person_key, p.display_name, p.relationship, p.summary, p.status, p.source,
       (SELECT s.handle FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'x'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS x_handle,
       (SELECT s.url FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'x'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS x_url,
       (SELECT s.handle FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'slack'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS slack_handle,
       (SELECT s.url FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'slack'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS slack_url,
       (SELECT s.handle FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'github'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS github_handle,
       (SELECT s.url FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'github'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS github_url,
       (SELECT s.handle FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'linkedin'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS linkedin_handle,
       (SELECT s.url FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'linkedin'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS linkedin_url,
       (SELECT s.handle FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'discord'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS discord_handle,
       (SELECT s.url FROM rl_social_accounts s WHERE s.person_key = p.person_key AND s.platform = 'discord'
         ORDER BY s.updated_at DESC, s.id DESC LIMIT 1) AS discord_url,
       (SELECT count(*) FROM rl_social_accounts s WHERE s.person_key = p.person_key) AS social_account_count,
       (SELECT count(*) FROM rl_interaction_notes n WHERE n.person_key = p.person_key) AS note_count,
       -- The latest meeting by its time in UTC, shown as written; occurred_at that doesn't parse sorts by created_at
       (SELECT coalesce(n.occurred_at, n.created_at) FROM rl_interaction_notes n
         WHERE n.person_key = p.person_key AND n.kind = 'meeting'
         ORDER BY coalesce(datetime(n.occurred_at), datetime(n.created_at)) DESC, n.id DESC LIMIT 1) AS last_met_at,
       (SELECT count(*) FROM rl_prompt_injection_events e WHERE e.person_key = p.person_key) AS prompt_injection_count,
       (SELECT count(*) FROM rl_photo_refs r WHERE r.person_key = p.person_key) AS photo_ref_count,
       p.created_at, p.updated_at
  FROM rl_people p;

-- Search entry point: every searchable text with the person it belongs to.
-- SELECT DISTINCT person_key FROM rl_v_search WHERE search_text LIKE '%' || rl_norm('<term>') || '%' ESCAPE '\'
CREATE VIEW IF NOT EXISTS rl_v_search AS
SELECT person_key, 'person' AS found_in, search_text FROM rl_people
UNION ALL
SELECT person_key, 'social_account' AS found_in, search_text FROM rl_social_accounts
UNION ALL
SELECT person_key, 'note' AS found_in, search_text FROM rl_interaction_notes;

INSERT INTO rl_schema_migrations (version) VALUES ('0001_init') ON CONFLICT (version) DO NOTHING;
