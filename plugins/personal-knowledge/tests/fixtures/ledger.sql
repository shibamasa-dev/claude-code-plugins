-- Fictional people only (example.com, @example_user and the like). Statements end with ';' at line end.
INSERT INTO rl_people (person_key, display_name, relationship, summary, status, source)
VALUES ('taro-example', '例 太郎 / Taro Example', 'Example Meetup #2 で名刺交換 / Example株式会社', '事業開発 / Example株式会社', 'active', 'user-provided business card');
INSERT INTO rl_people (person_key, display_name, relationship, status, source)
VALUES ('example-user', 'ＥＸＡＭＰＬＥ ユーザー', 'フォロワーで知り合い', 'watch', 'user');
INSERT INTO rl_people (person_key, display_name, relationship, status)
VALUES ('hanako-sample', 'Hanako Sample', 'former colleague', 'archived');
INSERT INTO rl_social_accounts (person_key, platform, handle, url)
VALUES ('example-user', 'x', 'example_user', 'https://x.com/example_user');
INSERT INTO rl_social_accounts (person_key, platform, handle, url)
VALUES ('taro-example', 'github', 'example-taro', 'https://github.com/example-taro');
INSERT INTO rl_interaction_notes (person_key, kind, note, confidence, occurred_at)
VALUES ('taro-example', 'meeting', 'event: Example Meetup #2; place: Example Hall; met_at: 2026-05-28T19:00:00+09:00; conversation: agent governance について会話', 4, '2026-05-28T19:00:00+09:00');
INSERT INTO rl_interaction_notes (person_key, kind, note, confidence)
VALUES ('taro-example', 'context', 'Business card fields: company: Example株式会社; title: 事業開発; email: taro@example.com', 4);
INSERT INTO rl_interaction_notes (person_key, kind, note)
VALUES ('taro-example', 'task', 'Follow-up: 資料URLを送る');
INSERT INTO rl_prompt_injection_events (person_key, source_kind, source_url, summary, severity, outcome)
VALUES ('example-user', 'x', 'https://x.com/example_user/status/1', 'Jokingly asked to rename an existing calendar event.', 'playful', 'no_calendar_update');
INSERT INTO rl_photo_refs (person_key, file_path, consent_basis)
VALUES ('taro-example', 'photos/taro-example.jpg', 'provided by the person');
