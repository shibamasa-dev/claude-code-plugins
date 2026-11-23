-- Image history schema, SQLite dialect. migrations/postgres/0001_init.sql is the same schema for Postgres.
--
-- The bundled MCP server applies this file when it first opens the database and registers img_norm(text) on every
-- connection (SQLite has no normalize()). The triggers call img_norm(), so a client without it (sqlite3, DB Browser)
-- can read every table but its writes to img_attempts fail with "no such function: img_norm".
-- Safe to run more than once: every statement is IF NOT EXISTS / ON CONFLICT DO NOTHING.
--
-- Never edit a file that has shipped: CREATE TABLE IF NOT EXISTS skips a table that exists, and the version is already
-- recorded. A later change goes in a new file (0002_<name>.sql) that alters what exists, for example ADD COLUMN.
--
-- Don't write BEGIN, COMMIT or ROLLBACK in a migration file (this one or any later one): the server runs
-- each file inside its own transaction, so it applies completely or not at all.
--
-- Timestamps are UTC text with milliseconds: 2026-11-23T09:30:00.123Z

CREATE TABLE IF NOT EXISTS img_schema_migrations (
  version    text PRIMARY KEY,
  applied_at text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- One row per image attempt: a plan, a generated image, a rejected draft, a variant or an edit.
-- A refinement is a new row whose based_on names the attempt it builds on; rows are not overwritten.
-- AUTOINCREMENT so that an id is never reused after a delete (other tables and notes refer to it).
CREATE TABLE IF NOT EXISTS img_attempts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        text NOT NULL CHECK (title <> ''),
  request      text NOT NULL,                -- the user's request, in their words, or a summary of it
  asset_type   text,                         -- '16:9 banner', 'app icon', 'hero image'
  style        text,                         -- rendering and taste
  composition  text,                         -- layout and reading order
  prompt       text,                         -- the final prompt (the five-section structure)
  route        text,                         -- the route id that generated it (codex, gemini, openai, fal, ...); NULL for a plan only
  output_paths text NOT NULL DEFAULT '[]' CHECK (json_valid(output_paths) AND json_type(output_paths) = 'array'),
  based_on     integer REFERENCES img_attempts (id),
  -- What this attempt reused from earlier references or attempts
  reuse_scope  text CHECK (reuse_scope IN ('composition_only', 'style_only', 'palette_only', 'typography_only',
                                           'subject_only', 'full_reference', 'none')),
  tags         text,                         -- comma-separated
  notes        text,                         -- feedback, failure notes, the reuse decision, IP-safety notes
  status       text NOT NULL DEFAULT 'planned'
               CHECK (status IN ('planned', 'generated', 'accepted', 'rejected', 'failed', 'superseded')),
  search_text  text,                         -- img_norm() of the text columns, maintained by triggers
  created_at   text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at   text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS img_attempts_created_ix ON img_attempts (created_at);

-- A reference image attached to an attempt, kept as a compact proxy under the plugin data directory.
-- role says what a later generation may borrow from it.
CREATE TABLE IF NOT EXISTS img_references (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  attempt_id    integer NOT NULL REFERENCES img_attempts (id) ON DELETE CASCADE,
  role          text NOT NULL DEFAULT 'full_reference'
                CHECK (role IN ('composition_only', 'style_only', 'palette_only', 'typography_only',
                                'subject_only', 'full_reference', 'none')),
  label         text,
  source_path   text NOT NULL,               -- where the original was, for provenance; never copied
  source_sha256 text NOT NULL CHECK (length(source_sha256) = 64),
  source_bytes  integer NOT NULL CHECK (source_bytes >= 0),
  proxy_ref     text,                        -- file name in the proxy folder; NULL when only notes are kept
  proxy_bytes   integer CHECK (proxy_bytes >= 0),
  width         integer CHECK (width >= 0),
  height        integer CHECK (height >= 0),
  max_edge      integer CHECK (max_edge > 0),
  format        text,
  notes         text,
  created_at    text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at    text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE (attempt_id, source_sha256)
);
CREATE INDEX IF NOT EXISTS img_references_role_ix ON img_references (role, attempt_id);

-- Triggers. A trigger that updates its own table names its columns (AFTER UPDATE OF ...) so that its
-- UPDATE never fires itself or the others again, whatever PRAGMA recursive_triggers says:
-- search_text and updated_at are in no trigger's column list.

CREATE TRIGGER IF NOT EXISTS img_attempts_search_text_ai AFTER INSERT ON img_attempts
BEGIN
  UPDATE img_attempts
     SET search_text = img_norm(NEW.title || ' ' || NEW.request || ' ' || coalesce(NEW.asset_type, '') || ' '
                                || coalesce(NEW.style, '') || ' ' || coalesce(NEW.composition, '') || ' '
                                || coalesce(NEW.prompt, '') || ' ' || coalesce(NEW.tags, '') || ' '
                                || coalesce(NEW.notes, ''))
   WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS img_attempts_search_text_au
AFTER UPDATE OF title, request, asset_type, style, composition, prompt, tags, notes ON img_attempts
BEGIN
  UPDATE img_attempts
     SET search_text = img_norm(NEW.title || ' ' || NEW.request || ' ' || coalesce(NEW.asset_type, '') || ' '
                                || coalesce(NEW.style, '') || ' ' || coalesce(NEW.composition, '') || ' '
                                || coalesce(NEW.prompt, '') || ' ' || coalesce(NEW.tags, '') || ' '
                                || coalesce(NEW.notes, ''))
   WHERE id = NEW.id;
END;

-- updated_at on every update of a real column (Claude's own UPDATE may leave it out)
CREATE TRIGGER IF NOT EXISTS img_attempts_updated_at AFTER UPDATE OF
  title, request, asset_type, style, composition, prompt, route, output_paths, based_on, reuse_scope, tags, notes,
  status, created_at ON img_attempts
BEGIN
  UPDATE img_attempts SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS img_references_updated_at AFTER UPDATE OF
  attempt_id, role, label, source_path, source_sha256, source_bytes, proxy_ref, proxy_bytes, width, height, max_edge,
  format, notes, created_at ON img_references
BEGIN
  UPDATE img_references SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = NEW.id;
END;

-- An id is the row's identity: other rows and notes refer to it
CREATE TRIGGER IF NOT EXISTS img_attempts_id_immutable BEFORE UPDATE OF id ON img_attempts
WHEN NEW.id IS NOT OLD.id
BEGIN
  SELECT RAISE(ABORT, 'img_attempts.id cannot change; insert a new row instead');
END;

CREATE TRIGGER IF NOT EXISTS img_references_id_immutable BEFORE UPDATE OF id ON img_references
WHEN NEW.id IS NOT OLD.id
BEGIN
  SELECT RAISE(ABORT, 'img_references.id cannot change; insert a new row instead');
END;

-- Search entry point: one row per attempt, with the roles of its references (comma-separated)
CREATE VIEW IF NOT EXISTS img_v_attempts AS
SELECT a.id, a.created_at, a.status, a.title, a.asset_type, a.style, a.composition, a.route, a.reuse_scope,
       a.based_on, a.tags, a.output_paths, a.notes, a.search_text, a.updated_at,
       (SELECT group_concat(role, ',') FROM (SELECT DISTINCT r.role FROM img_references r
                                              WHERE r.attempt_id = a.id ORDER BY r.role)) AS reference_roles
  FROM img_attempts a;

INSERT INTO img_schema_migrations (version) VALUES ('0001_init') ON CONFLICT (version) DO NOTHING;
