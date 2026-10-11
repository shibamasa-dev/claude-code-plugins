# Changelog

Change history of the lint plugin. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.2.0] - 2026-10-11

### Changed
- Messages, skill bodies, references, comments and tests are now in English. Japanese stays only in the skill descriptions' trigger phrases, in data the features need (patterns that match Japanese text, fixtures for Japanese input) and in `README.ja.md`.
- skill-lint: `lint.py --json` now reports `gitleaks.status` as `ran` / `skipped` / `failed` (was `実施` / `未実施` / `失敗`)
- tests: `run-all.sh` now ends with `==== N as expected / M mismatches ====` (was `==== 期待どおり N 件 / 食い違い M 件 ====`), and test rows end with `(expect <value>)` (was `(<value> 期待)`)

## [0.1.0] - 2026-10-09

- 初版（`skill-lint` スキル・`skill-creator-chain` フック）
