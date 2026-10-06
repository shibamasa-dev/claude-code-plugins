# Changelog

review プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.3.0] - 2026-10-06

### Added
- `dev-flow-gate` フック：PR 本文の `Closes` / `Refs` と `Arch-Review:` の欄が無い PR 作成、待ちを始めずに終えるターン（PR ごとに1回）、`Closes` 先の `## 結果` の記録が無いマージを止める。GitHub コネクタと `gh` の両方を見る

### Changed
- `pr-review-wait`・`pr-rereview`：自動マージのリポを、guards の設定 `merge_allowed_repos` からリポの `.claude/dev-flow.json` に切り替えた（移行中は `merge_allowed_repos` のリポも同じ扱い）

## [0.2.0] - 2026-10-06

### Added
- `dev-flow` スキル：issue の対応も口頭の依頼も、依頼からマージまでを1本のフローで回す入口。構造変更の基準とアーキレビュー、Issue Fields（`Arch Review`・`Verification`）が無いときの警告、実装後の自己レビュー、PR 本文の `Closes` / `Refs` と `Arch-Review:` の欄、マージ前の `## 結果`、リポ単位の自動マージ（`.claude/dev-flow.json`）を持つ

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `pr-review-wait`・`pr-rereview` とコマンド `review-and-fix` を移した（中身は変えていない）。コマンドは `/review:dev-process:review-and-fix` になる
