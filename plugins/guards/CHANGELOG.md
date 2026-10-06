# Changelog

guards プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.1.3] - 2026-10-06

### Added
- プラグインの README

### Changed
- plugin.json に `homepage`・`repository`・`keywords` を追加

## [0.1.2] - 2026-10-05

### Changed
- file-guard の規約ファイル `repo-structure.md` をプラグインに同梱し、既定にした。`~/.claude/rules/repo-structure.md` があればそちらが優先
- file-guard の skills 例外を、リポ相対パスで `scripts/` 直下のものだけに限定した

## [0.1.1] - 2026-10-04

- 公開リポでの初版（bash-guard・file-guard・full-test-gate・git-freshness）
