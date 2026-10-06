# Changelog

workflow プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.1.5] - 2026-10-06

### Added
- プラグインの README

### Changed
- plugin.json に `homepage`・`repository`・`keywords` を追加

## [0.1.4] - 2026-10-06

### Changed
- pr-review-wait：bot のレート制限・上限の合図を「未レビュー」として扱い、明けるのを待って頼み直す。上限のコメントしか出していない bot も待つ対象に入れ、summarize 以外のコメントで来た合図も状態行に出す
- pr-rereview：レート制限が明けた bot への頼み直しは、再レビュー基準に関係なくその bot にだけ投げてよい

## [0.1.3] - 2026-10-06

### Security
- openapi-to-skills：生成する auth スクリプトと SKILL.md に spec の値をそのまま埋め込まないようにした（frontmatter も引用する）
- openapi-to-skills：認証まわりの URL は https に限る（http は localhost・127.0.0.1 だけ）。文字列でない・欠けた・空の tokenUrl は拒否し、discovery の token_endpoint も https に限る

## [0.1.2] - 2026-10-04

- 公開リポでの初版（スキル 10 本・フック 6 本・コマンド `review-and-fix`）
