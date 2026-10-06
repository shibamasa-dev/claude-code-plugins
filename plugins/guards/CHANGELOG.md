# Changelog

guards プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.1.5] - 2026-10-06

### Removed
- `full-test-gate` を testing プラグインへ移した。引き続き使うには testing プラグインを入れる

## [0.1.4] - 2026-10-06

### Added
- プラグインの README

### Changed
- plugin.json に `homepage`・`repository`・`keywords` を追加

## [0.1.3] - 2026-10-06

### Fixed
- bash-guard のマージ前ゲート：前のセグメントで設定・export した `GH_REPO` や `-R`・URL も見て対象リポを決める。決めきれないときは例外にしない
- bash-guard：sudo・env・timeout などのラッパーの長いオプションや短いオプションの束も読んで、中のコマンドを判定する
- bash-guard の削除ガード：開始パスを省いた `find` はカレントからとして扱い、条件なしでカレントを消す `find` は `rm -rf .` と同じ扱いにする。`-exec`・`-ok` が実行するコマンドも判定する
- bash-guard：演算子つきの変数展開（`${NAME:-word}` など）と、子シェルの中の外側の変数は判定不能（安全側）にする
- bash-guard：`if`・`while`・`for`・`case` の中の cd・代入は、実行されるか分からないものとして扱う

## [0.1.2] - 2026-10-05

### Changed
- file-guard の規約ファイル `repo-structure.md` をプラグインに同梱し、既定にした。`~/.claude/rules/repo-structure.md` があればそちらが優先
- file-guard の skills 例外を、リポ相対パスで `scripts/` 直下のものだけに限定した

## [0.1.1] - 2026-10-04

- 公開リポでの初版（bash-guard・file-guard・full-test-gate・git-freshness）
