# Changelog

Change history of the lint plugin. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.4.2] - 2026-11-21

### Changed
- skill-lint's rule table quotes its Japanese decision words in backticks, so editing that line passes the repo's language check (#112).

## [0.4.1] - 2026-11-20

### Changed
- skill-lint keeps its working files (`lint.json`, `review.txt`, `review.json`) in the session scratchpad, or in a `mktemp -d` directory it removes after the report (#83).

## [0.4.0] - 2026-11-18

### Added
- `design-lint` hook (moved from the `creative` plugin): after Edit or Write on a `DESIGN.md`, runs `npx @google/design.md@latest lint` and returns the findings; says lint was not run when `npx` fails.

## [0.3.0] - 2026-11-17

### Added
- `skill-planner` skill: plans a skill before it is built (should it be a skill, smallest implementation level, contents, state location, validation) and hands off to `skill-creator`, then `skill-lint`. Plans state under `${CLAUDE_PLUGIN_DATA}`, never in the skill directory.

## [0.2.2] - 2026-10-13

### Removed
- skill-lint: the eval set (`evals/`, including its fixture) is no longer shipped. The maintainers keep it locally.

### Changed
- skill-lint: `scripts/run_evals.py` and `scripts/run_reviewer_eval.py` stop with a message saying the eval set is not published when `evals/evals.json` is missing.

## [0.2.1] - 2026-10-11

### Fixed
- skill-lint: provenance warnings also fire on English decision words (`approved`, `decided`, `confirmed`, `instructed`, `agreed`, `signed off`; whole words, any case) on a line with a date.

## [0.2.0] - 2026-10-11

### Changed
- Messages, skill bodies, references, comments and tests are now in English. Japanese stays only in the skill descriptions' trigger phrases, in data the features need (patterns that match Japanese text, fixtures for Japanese input) and in `README.ja.md`.
- skill-lint: `lint.py --json` now reports `gitleaks.status` as `ran` / `skipped` / `failed` (was `実施` / `未実施` / `失敗`)
- tests: `run-all.sh` now ends with `==== N as expected / M mismatches ====` (was `==== 期待どおり N 件 / 食い違い M 件 ====`), and test rows end with `(expect <value>)` (was `(<value> 期待)`)

## [0.1.0] - 2026-10-09

- 初版（`skill-lint` スキル・`skill-creator-chain` フック）
