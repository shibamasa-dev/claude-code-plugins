# Changelog

Change history of the repo-setup plugin (named devtools up to 0.2.2). Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.4.0] - 2026-10-11

### Changed
- Messages, skill bodies, references, comments and tests are now in English. Japanese stays only in the skill descriptions' trigger phrases, in data the features need (patterns that match Japanese text, fixtures for Japanese input) and in `README.ja.md`.
- remote-setup: the generated `scripts/remote-setup/*.sh` templates and the messages `setup.sh` prints into the session context (`[remote-setup] ...`) are now in English. Re-running `scaffold.py` overwrites an existing `setup.sh` with the English version; existing `steps.sh` / `environment-setup.sh` are kept as they are
- codebase-doctor: refers to the section of testing's `perspectives-common.md` as section 7, "Project-specific perspectives" (the heading the English testing plugin uses)

## [0.3.0] - 2026-10-11

### Changed
- **プラグインの名前を devtools から repo-setup に変えた。** 開発のどこで使うか（リポの立ち上げ）が名前から分かるようにするため。devtools を入れていたら外して repo-setup を入れる

### Removed
- 使用枠を書き出す mod（`rate-limits`）を workflow プラグインへ移した。書き出し先と形式は変わらない。引き続き使うには workflow を入れる

## [0.2.2] - 2026-10-10

### Changed
- codebase-doctor：testcase-generator が testing プラグインのスキルだと書き添えた

## [0.2.1] - 2026-10-10

### Changed
- remote-setup：ローカルの venv 運用への言及を外し、eval の入力を入れた人が用意できるリポの記述にした

## [0.2.0] - 2026-10-09

### Added
- 使用枠（rate limits）を `/tmp/claude-<uid>/rate-limits.json` へ書き出す mod（`hooks/rate-limits.ts`）。`session.start` と `session.measure` で `five_hour` / `seven_day` の `used_percentage`・`resets_at`・`seen_at` を書く。並列セッションの古い値ではなるべく上書きせず（ロックは無いベストエフォート）、本人専用ディレクトリ内で一時ファイル→`mv -f` で書く

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `codebase-doctor`・`remote-setup` を移した。`codebase-doctor` は testing プラグインの `testcase-generator` を名前で参照し、testing が無ければテスト設計の点検（Check 6b）を SKIP にする
