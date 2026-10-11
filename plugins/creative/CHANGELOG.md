# Changelog

Changelog of the creative plugin (named docs up to 0.1.4). Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow `version` in plugin.json.

## [0.3.1] - 2026-10-11

### Fixed
- motion-video: `brief-template.md` calls the first cut sheet v1 (it said v0; `render.mjs` writes v1 first).

## [0.3.0] - 2026-10-11

### Changed
- Messages, skill bodies, references, comments and tests are now in English. Japanese stays only in the skill descriptions' trigger phrases, in data the features need (patterns that match Japanese text, fixtures for Japanese input) and in `README.ja.md`.

## [0.2.0] - 2026-10-11

### Changed
- **プラグインの名前を docs から creative に変えた。** 中身は画像・動画・DESIGN.md で、文書ではないため（`design` は公式の同名プラグインがあるので避けた）。docs を入れていたら外して creative を入れる。スキル名とフックは変えていない

## [0.1.4] - 2026-10-10

### Changed
- motion-video：eval の題材 example-intro とブランドの例（`references/brand.example.json`）を、架空の家具店の紹介・別系統のパレットと書体に差し替えた。シーンの構成と時刻は変えていない

## [0.1.3] - 2026-10-06

### Added
- motion-video: 絵コンテの主な出力をカット表 `cutsheet.html` にした（1行＝1カット・はじめ/おわりの2コマ・開始と尺を秒と拍で・検証欄・FB 欄・タイムライン帯）
- motion-video: カット表の FB 往復と版。`feedback/v<N>.json` を置いて storyboard を回すと版が進み、前の版を `out/storyboard/v<N>/` に残し、「v<N> の FB への対応」表と新旧の比較画像を出す。対応の書き漏れを警告する
- motion-video: 雑メモ入口（brief-template）、音楽ブリーフのひな形と `music.mjs` への対応表（references/music-brief.md）、技術検証の段、実写テクスチャの重ね方と素材の請求表、生成画像を素材として受け入れる手順
- motion-video: 自己採点に「ありがち度」と「緩急」を追加（9項目）
- motion-video: eval「cutsheet-feedback-v1-v2」

## [0.1.2] - 2026-10-06

### Added
- プラグインの README

### Changed
- plugin.json に `homepage`・`repository`・`keywords` を追加

## [0.1.1] - 2026-10-04

- 公開リポでの初版（`image-generation-prompt`・`motion-video`・`design-lint`）
