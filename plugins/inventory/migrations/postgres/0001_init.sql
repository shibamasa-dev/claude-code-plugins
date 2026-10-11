-- Inventory schema, Postgres dialect (Postgres 13+, Supabase). migrations/sqlite/0001_init.sql is the same schema for SQLite.
--
-- Runs on its own, without the bundled MCP server: the server applies it at startup for database_url,
-- and over a connector Claude sends the whole file to the connector's migration tool (Supabase: apply_migration).
-- Safe to run more than once: IF NOT EXISTS, CREATE OR REPLACE, DROP TRIGGER IF EXISTS, ON CONFLICT DO NOTHING.
-- Objects go to the first schema on search_path (public on Supabase), hence the inv_ prefix.
--
-- Timestamps are UTC text with milliseconds, the same format as SQLite: 2026-10-11T09:30:00.123Z

-- The same norm() the MCP server registers on SQLite. Search with: search_text LIKE '%' || norm('<term>') || '%'
CREATE OR REPLACE FUNCTION norm(text) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
  AS $$ SELECT lower(normalize($1, NFKC)) $$;

CREATE OR REPLACE FUNCTION inv_now() RETURNS text
  LANGUAGE sql VOLATILE
  AS $$ SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') $$;

CREATE TABLE IF NOT EXISTS inv_schema_migrations (
  version    text PRIMARY KEY,
  applied_at text NOT NULL DEFAULT inv_now()
);

-- Categories stop spelling variants. Users add their own with INSERT.
--   kind is how you count and look for things:
--   part (counted components), consumable (used up: solder, wire), tool (one unit each), device (finished products)
CREATE TABLE IF NOT EXISTS inv_categories (
  code       text PRIMARY KEY CHECK (code <> ''),
  name       text NOT NULL,
  kind       text NOT NULL CHECK (kind IN ('part', 'consumable', 'tool', 'device')),
  sort       integer NOT NULL DEFAULT 0,
  created_at text NOT NULL DEFAULT inv_now(),
  updated_at text NOT NULL DEFAULT inv_now()
);

-- One row per item. item_key is a slug such as 'breadboard-830' that Claude picks once and never changes:
-- deriving identity from descr would turn a one-character edit of the description into a new item.
CREATE TABLE IF NOT EXISTS inv_items (
  item_key      text PRIMARY KEY CHECK (item_key <> ''),
  category      text NOT NULL REFERENCES inv_categories (code),
  descr         text NOT NULL,                -- one human-readable line
  mpn           text,                         -- manufacturer part number; NULL for generic bagged parts
  manufacturer  text,
  package       text,
  value_display text,                         -- as printed: '4k7', '0.1u', '680R'
  value_si      double precision,             -- the main value in SI units (ohm, F, H); NULL for tools and devices
  unit          text,                         -- 'ohm', 'F', 'H', 'V', 'A', 'Hz'
  aliases       text,                         -- other spellings and names, comma-separated (NFKC folds width, not kana/kanji/English)
  attrs         jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(attrs) = 'object'),
  qty           integer CHECK (qty >= 0),     -- NULL = not counted, 0 = none left. attrs.pack_qty is the pack size, not this
  location      text,                         -- where it is kept, free text
  vendor        text,
  vendor_pn     text,
  url           text,
  datasheet_url text,
  photo_ref     text,                         -- relative path, URL or ID of the photo the row was read from
  photo_sha256  text,
  -- Columns that couldn't be read or were guessed, comma-separated without spaces ('qty,manufacturer', 'attrs.remaining').
  -- NULL = everything confirmed. Names, not a boolean, because "read the part number but not the rating" is normal for photos
  needs_review  text CHECK (needs_review <> '' AND needs_review NOT LIKE '% %'),
  note          text,
  search_text   text,                         -- norm(descr, mpn, manufacturer, aliases), maintained by a trigger
  created_at    text NOT NULL DEFAULT inv_now(),
  updated_at    text NOT NULL DEFAULT inv_now()
);
CREATE UNIQUE INDEX IF NOT EXISTS inv_items_mpn_ux ON inv_items (manufacturer, mpn) WHERE mpn IS NOT NULL;
CREATE INDEX IF NOT EXISTS inv_items_category_ix ON inv_items (category, value_si);
CREATE INDEX IF NOT EXISTS inv_items_review_ix ON inv_items (needs_review) WHERE needs_review IS NOT NULL;

-- Triggers

CREATE OR REPLACE FUNCTION inv_set_updated_at() RETURNS trigger
  LANGUAGE plpgsql
  AS $$ BEGIN NEW.updated_at := inv_now(); RETURN NEW; END $$;

CREATE OR REPLACE FUNCTION inv_items_set_search_text() RETURNS trigger
  LANGUAGE plpgsql
  AS $$
BEGIN
  NEW.search_text := norm(NEW.descr || ' ' || coalesce(NEW.mpn, '') || ' ' || coalesce(NEW.manufacturer, '')
                          || ' ' || coalesce(NEW.aliases, ''));
  RETURN NEW;
END $$;

-- TG_ARGV[0] names the key column. Changing a key would silently turn one row into another
CREATE OR REPLACE FUNCTION inv_reject_key_change() RETURNS trigger
  LANGUAGE plpgsql
  AS $$
BEGIN
  IF to_jsonb(NEW) -> TG_ARGV[0] IS DISTINCT FROM to_jsonb(OLD) -> TG_ARGV[0] THEN
    RAISE EXCEPTION '%.% cannot change; insert a new row instead', TG_TABLE_NAME, TG_ARGV[0];
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS inv_items_search_text ON inv_items;
CREATE TRIGGER inv_items_search_text BEFORE INSERT OR UPDATE ON inv_items
  FOR EACH ROW EXECUTE FUNCTION inv_items_set_search_text();

DROP TRIGGER IF EXISTS inv_items_updated_at ON inv_items;
CREATE TRIGGER inv_items_updated_at BEFORE UPDATE ON inv_items
  FOR EACH ROW EXECUTE FUNCTION inv_set_updated_at();

DROP TRIGGER IF EXISTS inv_items_item_key_immutable ON inv_items;
CREATE TRIGGER inv_items_item_key_immutable BEFORE UPDATE OF item_key ON inv_items
  FOR EACH ROW EXECUTE FUNCTION inv_reject_key_change('item_key');

DROP TRIGGER IF EXISTS inv_categories_updated_at ON inv_categories;
CREATE TRIGGER inv_categories_updated_at BEFORE UPDATE ON inv_categories
  FOR EACH ROW EXECUTE FUNCTION inv_set_updated_at();

DROP TRIGGER IF EXISTS inv_categories_code_immutable ON inv_categories;
CREATE TRIGGER inv_categories_code_immutable BEFORE UPDATE OF code ON inv_categories
  FOR EACH ROW EXECUTE FUNCTION inv_reject_key_change('code');

-- Search entry point
CREATE OR REPLACE VIEW inv_v_items AS
SELECT i.item_key, c.kind, i.category, c.name AS category_name,
       i.descr, i.mpn, i.manufacturer, i.package, i.value_display, i.value_si, i.unit,
       i.qty, i.location, i.aliases, i.attrs, i.vendor, i.vendor_pn, i.datasheet_url,
       i.photo_ref, i.needs_review, i.note, i.search_text, i.updated_at
  FROM inv_items i
  JOIN inv_categories c ON c.code = i.category;

-- Rows that need a look at the real thing before they can be trusted
CREATE OR REPLACE VIEW inv_v_needs_review AS
SELECT i.item_key, i.descr, i.needs_review AS fields, i.qty, i.location, i.photo_ref, i.note
  FROM inv_items i
 WHERE i.needs_review IS NOT NULL;

-- Row level security on, with no policies: only the table owner (the direct connection or the connector) sees rows.
ALTER TABLE inv_schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE inv_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE inv_items ENABLE ROW LEVEL SECURITY;

-- Views run with their owner's rights and would bypass RLS. On Supabase, new objects in public are granted to
-- the API roles anon and authenticated by default, so take the views away from them where those roles exist.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON inv_v_items, inv_v_needs_review FROM %I', r);
    END IF;
  END LOOP;
END $$;

INSERT INTO inv_categories (code, name, kind, sort) VALUES
  ('resistor',     'Resistors',                         'part',        10),
  ('capacitor',    'Capacitors',                        'part',        20),
  ('inductor',     'Inductors and ferrites',            'part',        30),
  ('diode',        'Diodes',                            'part',        40),
  ('transistor',   'Transistors and FETs',              'part',        50),
  ('ic',           'ICs',                               'part',        60),
  ('module',       'Modules and boards',                'part',        70),
  ('crystal',      'Crystals and oscillators',          'part',        80),
  ('led',          'LEDs and displays',                 'part',        90),
  ('switch',       'Switches and encoders',             'part',       100),
  ('connector',    'Connectors and pin headers',        'part',       110),
  ('jumper',       'Jumper wires and test leads',       'part',       115),
  ('sensor',       'Sensors',                           'part',       120),
  ('power',        'Batteries and power parts',         'part',       130),
  ('mechanical',   'Screws, spacers and mechanical parts', 'part',    140),
  ('wire',         'Wire and cables',                   'consumable', 200),
  ('solder',       'Solder and flux',                   'consumable', 210),
  ('adhesive',     'Adhesives, tape and heat shrink',   'consumable', 220),
  ('filament',     'Filament and resin',                'consumable', 230),
  ('tool_hand',    'Hand tools',                        'tool',       300),
  ('tool_solder',  'Soldering equipment',               'tool',       310),
  ('tool_meas',    'Test equipment and power supplies', 'tool',       320),
  ('tool_machine', 'Machines and 3D printers',          'tool',       330),
  ('tool_jig',     'Jigs, breadboards and programmers', 'tool',       340),
  ('device',       'Finished and self-built devices',   'device',     400),
  ('network',      'Network equipment',                 'device',     410),
  ('misc',         'Other and unsorted',                'part',       900)
ON CONFLICT (code) DO NOTHING;

INSERT INTO inv_schema_migrations (version) VALUES ('0001_init') ON CONFLICT (version) DO NOTHING;
