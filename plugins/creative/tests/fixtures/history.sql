-- Attempts and references taken from a real image history kept by the skill this one replaces.
-- Rows that named people or private systems are left out; machine paths are replaced; everything else is as recorded
-- (requests in the user's words, prompts, tags, sizes and hashes). Runs on SQLite and Postgres.
-- Statements end with ';' at the end of a line (tests/mcp_call.py --file splits there).

INSERT INTO img_attempts (title, request, asset_type, style, composition, prompt, route, output_paths, reuse_scope, tags, notes, status)
VALUES ('Mecha raid announcement banner',
        'こんな感じの構図の画像作れる？ 参照画像のようなゲーム告知バナーをオリジナルで生成。',
        '16:9 anime game update banner',
        'high-energy anime sci-fi promotional art',
        'top-left date/update strip; left tilted character portrait cut-in; right dominant giant original mecha; red diagonal lightning background; huge stylized Japanese event title across bottom third',
        'Create an original IP-safe anime sci-fi game announcement banner using the reference for composition only: left character cut-in, right large mecha, bottom event typography, red lightning action background, no real logos or existing IP likeness.',
        'codex',
        '["out/mecha-raid-banner.png"]',
        'composition_only',
        '16:9,banner,anime,game-update,mecha,left-cutin,bottom-title,red-lightning,reference-composition,accepted',
        'User liked the result. Preserve reusable planning pattern, not original IP details.',
        'accepted');

INSERT INTO img_attempts (title, request, asset_type, style, composition, prompt, route, output_paths, based_on, reuse_scope, tags, notes, status)
VALUES ('Original mecha announcement banner v2',
        'メカ告知バナー作って欲しいの',
        '16:9 anime sci-fi game announcement banner',
        'high-energy anime sci-fi promotional art with sharp cel shading, neon glow, dense arcade typography',
        'top-left update strip; left tilted anime pilot cut-in; right dominant giant original humanoid mecha lunging forward; red plasma lightning battlefield; huge Japanese lower-third event title',
        'Create a new original IP-safe mecha announcement banner. Reuse prior attempt #1 safely for composition and style energy: left tilted pilot cut-in, dominant right mecha, bottom Japanese event title, red lightning, high-contrast anime game promo finish. Text: 5/18(月) アップデート実施, 機甲レイド参戦!!, 紅雷の機兵, 緊急出撃!.',
        'codex',
        '["out/mecha-announcement-banner-v2.png"]',
        (SELECT id FROM img_attempts WHERE title = 'Mecha raid announcement banner'),
        'full_reference',
        '16:9,banner,anime,game-update,mecha,left-cutin,bottom-title,red-lightning,style-reference,composition-reference',
        'Generated after user clarified they wanted an actual mecha announcement banner. Uses prior #1 composition/style references abstractly and remains original/IP-safe.',
        'generated');

INSERT INTO img_references (attempt_id, role, label, source_path, source_sha256, source_bytes, proxy_ref, proxy_bytes, width, height, max_edge, format, notes)
VALUES ((SELECT id FROM img_attempts WHERE title = 'Mecha raid announcement banner'), 'composition_only', 'game-update-banner-reference',
        'upload/参考バナー.png', '35545b93150d77b927d3b64bf0a1a4381ca3f2f810106d3f4c68ea6ffd7f6a4e', 498132,
        '35545b93150d77b9-1280-q82.jpg', 60436, 564, 307, 1280, 'jpg', 'Compact visual proxy for future recreation.');

INSERT INTO img_references (attempt_id, role, label, source_path, source_sha256, source_bytes, proxy_ref, proxy_bytes, width, height, max_edge, format, notes)
VALUES ((SELECT id FROM img_attempts WHERE title = 'Mecha raid announcement banner'), 'style_only', 'accepted-output-style-reference',
        'out/mecha-raid-banner.png', 'df012721a956de725ebf2ddb2f155ed7f8b3ab20c344406e0d0642efa2f8e0ad', 2883580,
        'df012721a956de72-1280-q82.jpg', 303122, 1280, 720, 1280, 'jpg', 'Compact proxy of accepted generated output for future style-only reuse: anime sci-fi promo rendering, glow, contrast, title energy, detail density.');

INSERT INTO img_references (attempt_id, role, label, source_path, source_sha256, source_bytes, proxy_ref, proxy_bytes, width, height, max_edge, format, notes)
VALUES ((SELECT id FROM img_attempts WHERE title = 'Original mecha announcement banner v2'), 'style_only', 'mecha-announcement-v2-style-reference',
        'out/mecha-announcement-banner-v2.png', '3d21bcdebd6d485b241d8bef7f65e4b50ab50288593e15ecfd40dcec45f361db', 3195561,
        '3d21bcdebd6d485b-1280-q82.jpg', 343919, 1280, 720, 1280, 'jpg', 'Compact proxy of generated v2 banner for future style-only reuse.');
