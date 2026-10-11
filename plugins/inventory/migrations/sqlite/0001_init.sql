-- Inventory schema, SQLite dialect. migrations/postgres/0001_init.sql is the same schema for Postgres.
--
-- The bundled MCP server applies this file at startup and registers norm(text) on every connection
-- (SQLite has no normalize()). The triggers call norm(), so a client without it (sqlite3, DB Browser)
-- can read every table but its writes to inv_items fail with "no such function: norm".
-- Safe to run more than once: every statement is IF NOT EXISTS / ON CONFLICT DO NOTHING.
--
-- Timestamps are UTC text with milliseconds: 2026-10-11T09:30:00.123Z

CREATE TABLE IF NOT EXISTS inv_schema_migrations (
  version    text PRIMARY KEY,
  applied_at text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Categories stop spelling variants. Users add their own with INSERT.
--   kind is how you count and look for things:
--   part (counted components), consumable (used up: solder, wire), tool (one unit each), device (finished products)
CREATE TABLE IF NOT EXISTS inv_categories (
  code       text PRIMARY KEY CHECK (code <> ''),
  name       text NOT NULL,
  kind       text NOT NULL CHECK (kind IN ('part', 'consumable', 'tool', 'device')),
  sort       integer NOT NULL DEFAULT 0,
  created_at text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
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
  value_si      real,                         -- the main value in SI units (ohm, F, H); NULL for tools and devices
  unit          text,                         -- 'ohm', 'F', 'H', 'V', 'A', 'Hz'
  aliases       text,                         -- other spellings and names, comma-separated (NFKC folds width, not kana/kanji/English)
  attrs         text NOT NULL DEFAULT '{}' CHECK (json_valid(attrs) AND json_type(attrs) = 'object'),
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
  search_text   text,                         -- norm(descr, mpn, manufacturer, aliases), maintained by triggers
  created_at    text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  updated_at    text NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS inv_items_mpn_ux ON inv_items (manufacturer, mpn) WHERE mpn IS NOT NULL;
CREATE INDEX IF NOT EXISTS inv_items_category_ix ON inv_items (category, value_si);
CREATE INDEX IF NOT EXISTS inv_items_review_ix ON inv_items (needs_review) WHERE needs_review IS NOT NULL;

-- Triggers. A trigger that updates its own table names its columns (AFTER UPDATE OF ...) so that its
-- UPDATE never fires itself or the others again, whatever PRAGMA recursive_triggers says:
-- search_text and updated_at are in no trigger's column list.

-- search_text on insert
CREATE TRIGGER IF NOT EXISTS inv_items_search_text_ai AFTER INSERT ON inv_items
BEGIN
  UPDATE inv_items
     SET search_text = norm(NEW.descr || ' ' || coalesce(NEW.mpn, '') || ' ' || coalesce(NEW.manufacturer, '')
                            || ' ' || coalesce(NEW.aliases, ''))
   WHERE item_key = NEW.item_key;
END;

-- search_text when a source column changes
CREATE TRIGGER IF NOT EXISTS inv_items_search_text_au AFTER UPDATE OF descr, mpn, manufacturer, aliases ON inv_items
BEGIN
  UPDATE inv_items
     SET search_text = norm(NEW.descr || ' ' || coalesce(NEW.mpn, '') || ' ' || coalesce(NEW.manufacturer, '')
                            || ' ' || coalesce(NEW.aliases, ''))
   WHERE item_key = NEW.item_key;
END;

-- updated_at on every update of a real column (Claude's own UPDATE may leave it out)
CREATE TRIGGER IF NOT EXISTS inv_items_updated_at AFTER UPDATE OF
  category, descr, mpn, manufacturer, package, value_display, value_si, unit, aliases, attrs, qty, location,
  vendor, vendor_pn, url, datasheet_url, photo_ref, photo_sha256, needs_review, note, created_at ON inv_items
BEGIN
  UPDATE inv_items SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE item_key = NEW.item_key;
END;

-- item_key is the identity: changing it would silently turn one item into another
CREATE TRIGGER IF NOT EXISTS inv_items_item_key_immutable BEFORE UPDATE OF item_key ON inv_items
WHEN NEW.item_key IS NOT OLD.item_key
BEGIN
  SELECT RAISE(ABORT, 'inv_items.item_key cannot change; insert a new row and delete the old one instead');
END;

CREATE TRIGGER IF NOT EXISTS inv_categories_updated_at AFTER UPDATE OF name, kind, sort, created_at ON inv_categories
BEGIN
  UPDATE inv_categories SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE code = NEW.code;
END;

CREATE TRIGGER IF NOT EXISTS inv_categories_code_immutable BEFORE UPDATE OF code ON inv_categories
WHEN NEW.code IS NOT OLD.code
BEGIN
  SELECT RAISE(ABORT, 'inv_categories.code cannot change; add a new category instead');
END;

-- Search entry point
CREATE VIEW IF NOT EXISTS inv_v_items AS
SELECT i.item_key, c.kind, i.category, c.name AS category_name,
       i.descr, i.mpn, i.manufacturer, i.package, i.value_display, i.value_si, i.unit,
       i.qty, i.location, i.aliases, i.attrs, i.vendor, i.vendor_pn, i.datasheet_url,
       i.photo_ref, i.needs_review, i.note, i.search_text, i.updated_at
  FROM inv_items i
  JOIN inv_categories c ON c.code = i.category;

-- Rows that need a look at the real thing before they can be trusted
CREATE VIEW IF NOT EXISTS inv_v_needs_review AS
SELECT i.item_key, i.descr, i.needs_review AS fields, i.qty, i.location, i.photo_ref, i.note
  FROM inv_items i
 WHERE i.needs_review IS NOT NULL;

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
