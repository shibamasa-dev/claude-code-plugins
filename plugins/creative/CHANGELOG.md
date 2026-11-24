# Changelog

Changelog of the creative plugin (named docs up to 0.1.4). Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow `version` in plugin.json.

## [0.8.0] - 2026-11-23

### Added
- Image history for image-generation-prompt: search earlier attempts before planning, record every attempt (whatever the route), and keep reference images as compact JPEG proxies with a role saying what may be reused.
- A bundled MCP server `history` (`execute_sql`, `apply_migrations`) and migrations for SQLite and Postgres. SQLite under the plugin data directory by default; `userConfig` `sqlite_path`, `database_url`, `route` (`sqlite`, `postgres` or `connector`, saved by Claude on first use) and `connector_id` / `connector_project_id` for a claude.ai connector. When the saved route's setting is missing the server stops instead of opening another store, and its errors never show `database_url` or its password. Uninstalling the plugin deletes the default history unless `--keep-data` is passed.
- `scripts/history.py proxy`: makes the proxy under the plugin data directory and prints the values to record.
- Tests (`tests/run-all.sh`, `tests/run-postgres.sh`).

### Changed
- The plugin now starts an MCP server, which needs [uv](https://docs.astral.sh/uv/). Without uv the `history` server fails to start; the rest of the plugin still works. The SQLite history downloads no packages; psycopg is fetched into uv's cache only when `database_url` is used, and Pillow on the first proxy.

## [0.7.0] - 2026-11-23

### Added
- image-generation-prompt proposes image assets when they would improve a page, app, deck, document or article (count, use, style, route, rough cost), generates only after the user approves, matches the style of earlier assets, and never leaves the Constraints section empty.
- `userConfig` `image_routes` and `video_routes`: the route ids to try, in order (`codex`, `gemini`, `openai`, `fal`). Empty means Claude asks.
- `references/routes.md`: how to call each route, save to an absolute path and check the saved file.

### Changed
- image-generation-prompt no longer defers the route priority to a separate rule file of the user's; it reads the routes from the plugin settings.

## [0.6.0] - 2026-11-21

### Removed
- The `diagram-frames` skill.

## [0.5.1] - 2026-11-20

### Changed
- motion-video names the project folder: the one the user names, else `motion-video/<slug>/` under the working directory; `brief.md`, `music-brief.md` and `verify.md` go directly in it (#83).

## [0.5.0] - 2026-11-18

### Removed
- The `design-lint` hook moved to the `lint` plugin. If you relied on it, install `lint` (`/plugin install lint@shibamasa-plugins`). The plugin no longer has hooks.

## [0.4.0] - 2026-11-17

### Added
- `diagram-frames` skill: read before drawing an architecture, flow, sequence or state diagram as markup or code. It declares in one line what a box stands for (components, process steps, actors or states), puts that in the caption or legend, checks every box against it, and splits the figure in two instead of mixing kinds.
- motion-video: `last_reviewed` / `review_after` frontmatter, the same review dates the plugin's other skills carry.

## [0.3.3] - 2026-10-13

### Removed
- motion-video: the eval set (`evals/`) is no longer shipped. The maintainers keep it locally; the skill no longer tells you to run `evals/run.sh`.

## [0.3.2] - 2026-10-12

### Fixed
- motion-video: the skill description is 996 characters (it was 1,287). claude.ai cuts a description at 1,024 characters when it syncs the plugin, so the end of the trigger list and the limits were lost there.

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
