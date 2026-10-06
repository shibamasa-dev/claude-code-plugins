# Changelog

testing プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.1.1] - 2026-10-06

### Fixed
- full-test-gate：`base` を設定していないときの比較先を `origin/main` 固定から既定ブランチにした。origin に問い合わせ、繋がらなければ手元の origin/HEAD、それも無ければ `origin/main`。通知と止めるときのメッセージも、その比較先の名前を出す
- full-test-gate：origin が既定ブランチを変えて手元に `origin/<既定>` がまだ無いときは1回だけ取ってくる（取れなければ手元の origin/HEAD を使う）。比較できないとき（ref が無いなど）を「変更 0 件」と取り違えず、`status` と開始時の通知でそう伝える。`run` は比較先が読めなければ記録しない

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `testcase-generator` と `testcase-lint`、guards プラグインから `full-test-gate` を移した（中身は変えていない）
