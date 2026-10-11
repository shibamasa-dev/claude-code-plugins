-- Rows taken from a real inventory registered from photos (item_key, category, part number, maker, description,
-- aliases, needs_review as recorded). attrs is trimmed to a few non-identifying keys; notes, photo paths,
-- serial numbers, lot and JAN codes, prices and where things were bought are left out.
-- Written in the registration form SKILL.md teaches, so this file also checks that the form runs on SQLite and Postgres.
-- qty is omitted on purpose for switch-push-white-rect (not counted yet).
INSERT INTO inv_items (item_key, category, descr, mpn, manufacturer, aliases, attrs, qty, needs_review)
VALUES ('flux-hakko-fs812', 'solder', 'HAKKO FLUX FS-812 ハロゲンフリーフラックス 10ml', 'FS-812', '白光（HAKKO）',
        'フラックス,flux,hakko,白光,ハロゲンフリー,はんだ付け補助,fs-812', '{"volume_ml": 10, "halogen_free": true}', 1, 'attrs.remaining')
ON CONFLICT (item_key) DO UPDATE SET descr = excluded.descr, mpn = excluded.mpn, manufacturer = excluded.manufacturer,
        aliases = excluded.aliases, attrs = excluded.attrs, qty = excluded.qty, needs_review = excluded.needs_review;
INSERT INTO inv_items (item_key, category, descr, mpn, manufacturer, package, aliases, attrs, qty, needs_review)
VALUES ('iron-alientek-t80', 'tool_solder', 'ALIENTEK T80 スマートはんだごて（USB-C 電源・OLED 表示）', 'T80', 'ALIENTEK', 'box',
        'はんだごて,はんだコテ,半田ごて,ハンダゴテ,電烙鉄,soldering iron,t80,alientek,正点原子,smart soldering iron',
        '{"display": "OLED", "model_variant": "T80"}', 1, 'attrs.tip_type')
ON CONFLICT (item_key) DO UPDATE SET descr = excluded.descr, qty = excluded.qty, needs_review = excluded.needs_review;
INSERT INTO inv_items (item_key, category, descr, mpn, manufacturer, value_display, value_si, unit, package, aliases, attrs, qty)
VALUES ('resistor-cf25j680rb', 'resistor', 'カーボン抵抗 680Ω 1/4W 5%', 'CF25J680RB', 'FAITHFUL LINK', '680R', 680, 'ohm', 'THT',
        '炭素皮膜抵抗,カーボンフィルム抵抗,carbon film resistor,680オーム', '{"pack_qty": 100, "power_w": 0.25, "tolerance_pct": 5}', 100)
ON CONFLICT (item_key) DO UPDATE SET descr = excluded.descr, qty = excluded.qty;
INSERT INTO inv_items (item_key, category, descr, aliases, attrs, qty, needs_review)
VALUES ('jumper-breadboard-mm', 'jumper', 'ブレッドボード用ジャンパーワイヤ 両端オスピン（多色・束）',
        'ジャンパーワイヤ,ジャンパー線,ブレッドボードワイヤ,jumper wire,breadboard jumper,オスオス,male-male',
        '{"gender": "male-male", "housing": false}', 50, 'qty')
ON CONFLICT (item_key) DO UPDATE SET descr = excluded.descr, qty = excluded.qty, needs_review = excluded.needs_review;
INSERT INTO inv_items (item_key, category, descr, mpn, manufacturer, package, aliases, attrs, qty)
VALUES ('module-m5-stamp-s3a-pin254', 'module', 'M5Stamp S3A（PIN2.54版）ESP32-S3 スタンプモジュール', 'S007-PIN254-V033', 'M5Stack',
        'スタンプモジュール（2.54mmピッチ・ピンヘッダ実装済み）', 'm5stamp,m5stamps3a,stamp s3a,スタンプ,esp32-s3,esp32s3,pin2.54',
        '{"flash_mb": 8, "pitch_mm": 2.54}', 1)
ON CONFLICT (item_key) DO UPDATE SET descr = excluded.descr, qty = excluded.qty;
INSERT INTO inv_items (item_key, category, descr, package, aliases, attrs)
VALUES ('switch-push-white-rect', 'switch', '小型プッシュスイッチ（黒ボディ・白角プランジャ・スルーホール）型番不明', 'THT',
        'スイッチ,プッシュスイッチ,タクトスイッチ,押しボタン,switch,push switch,tactile', '{}')
ON CONFLICT (item_key) DO UPDATE SET descr = excluded.descr;
