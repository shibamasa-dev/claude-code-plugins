#!/bin/bash
# The write forms references/history.md teaches, run as written: they must work on SQLite and Postgres alike.
set -u
. "$(dirname "$0")/lib.sh"

fresh_db
load_fixtures
first="(SELECT id FROM img_attempts WHERE title = 'Mecha raid announcement banner')"

# Eval 2: 「前に作ったレイド告知っぽい構図で、今度は和風ファンタジーの鬼ボス討伐イベントにして。」 -> a new linked attempt
id=$(val "INSERT INTO img_attempts (title, request, asset_type, style, composition, prompt, route, output_paths, based_on, reuse_scope, tags, notes, status)
          VALUES ('Oni boss raid banner', '前に作ったレイド告知っぽい構図で、今度は和風ファンタジーの鬼ボス討伐イベントにして。', '16:9 game event banner',
                  'Japanese fantasy, ink and gold accents', 'left portrait cut-in, right giant oni boss, bottom event title', 'Scene: …', 'gemini',
                  '[\"/abs/out/oni-raid.png\"]', $first, 'composition_only', '16:9,banner,oni,raid', 'Reuses #1 composition only.', 'generated')
          RETURNING id")
is_id() { [[ "$id" =~ ^[0-9]+$ ]]; }
row 'INSERT ... RETURNING id gives the new id' "$(yesno is_id)" 'yes'
row 'the new attempt points at the one it builds on' "$(yesno [ "$(val "SELECT based_on FROM img_attempts WHERE id = $id")" = "$(val "SELECT id FROM img_attempts WHERE title = 'Mecha raid announcement banner'")" ])" 'yes'
row 'the earlier attempt is left as it was' "$(val "SELECT status FROM img_attempts WHERE title = 'Mecha raid announcement banner'")" 'accepted'
row 'the route is recorded whatever it is' "$(val "SELECT route FROM img_attempts WHERE id = $id")" 'gemini'

sql "UPDATE img_attempts SET status = 'accepted', notes = coalesce(notes || ' ', '') || 'User liked the ink style.' WHERE id = $id" >/dev/null
row 'the feedback update keeps the earlier notes' "$(yesno grep -qF 'Reuses #1 composition only. User liked the ink style.' <<<"$(val "SELECT notes FROM img_attempts WHERE id = $id")")" 'yes'

ref="INSERT INTO img_references (attempt_id, role, label, source_path, source_sha256, source_bytes, proxy_ref, proxy_bytes, width, height, max_edge, format, notes)
     VALUES ($id, 'ROLE', '鬼ボス参考', 'upload/鬼ボス参考.png', '3d21bcdebd6d485b241d8bef7f65e4b50ab50288593e15ecfd40dcec45f361db', 3195561,
             '3d21bcdebd6d485b-1280-q82.jpg', 343919, 1280, 720, 1280, 'jpg', NULL)
     ON CONFLICT (attempt_id, source_sha256) DO UPDATE SET role = excluded.role, label = excluded.label, notes = excluded.notes"
sql "${ref/ROLE/full_reference}" "${ref/ROLE/style_only}" >/dev/null
row 'recording the same reference twice updates its role instead of adding a row' "$(val "SELECT count(*) || ',' || max(role) FROM img_references WHERE attempt_id = $id")" '1,style_only'
