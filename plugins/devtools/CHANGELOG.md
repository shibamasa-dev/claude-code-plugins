# Changelog

devtools プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `codebase-doctor`・`remote-setup` を移した。`codebase-doctor` は testing プラグインの `testcase-generator` を名前で参照し、testing が無ければテスト設計の点検（Check 6b）を SKIP にする
