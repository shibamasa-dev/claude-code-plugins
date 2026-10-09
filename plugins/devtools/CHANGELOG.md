# Changelog

devtools プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.2.0] - 2026-10-09

### Added
- 使用枠（rate limits）を `/tmp/claude-<uid>/rate-limits.json` へ書き出す mod（`hooks/rate-limits.ts`）。`session.start` と `session.measure` で `five_hour` / `seven_day` の `used_percentage`・`resets_at`・`seen_at` を書く。並列セッションの古い値では上書きせず、本人専用ディレクトリ内で一時ファイル→`mv -f` で書く

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `codebase-doctor`・`remote-setup` を移した。`codebase-doctor` は testing プラグインの `testcase-generator` を名前で参照し、testing が無ければテスト設計の点検（Check 6b）を SKIP にする
