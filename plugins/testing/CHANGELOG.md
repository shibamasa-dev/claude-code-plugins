# Changelog

Change history of the testing plugin. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.3.0] - 2026-10-12

### Removed
- The top-level `bin/` directory (`full-test-gate`, `testcase-lint`), so the plugin can be added to a claude.ai marketplace. The bare `full-test-gate` / `testcase-lint` commands are no longer on PATH.

### Changed
- full-test-gate runs as `python3 "<plugin root>/hooks/full-test-gate.py" run|status`. The SessionStart notice and the PreToolUse deny reason print that command with the absolute path; the README uses `${CLAUDE_PLUGIN_ROOT}`.
- testcase-generator: the manual hook check pipes into `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/testcase-lint.py"`. The `command -v testcase-lint` wiring probe is gone; the manual run is the check.

## [0.2.1] - 2026-10-11

### Fixed
- testcase-lint: files whose Gherkin uses Japanese keywords (`シナリオ:`) are checked too (they were skipped because only `Scenario` was looked for).
- testcase-lint: English vague words match as whole words in any case, so `Properly` is caught and `incorrectly` no longer blocks; Japanese words still match as substrings.
- testcase-generator: eval case 0 accepts "Not applicable" perspectives (with a one-line reason), as SKILL.md requires.

## [0.2.0] - 2026-10-11

### Changed
- Messages, skill bodies, references, comments and tests are now in English. Japanese stays only in the skill descriptions' trigger phrases, in data the features need (patterns that match Japanese text, fixtures for Japanese input) and in `README.ja.md`.
- testcase-lint: the vague-word list in the style guide (`lint:vague-words`) now also blocks the English words "correctly", "appropriately", "properly", "without problems", "reasonably" and "works normally". The Japanese words are still blocked
- testcase-generator: the output section headings are now English (`## Scope`, `## Perspective decisions`, `## Test cases`, `## Self-check`, `## Execution path`, `## Points to confirm`, `## Proposed additions to the common perspectives`), and the section contents are written in the user's language

## [0.1.4] - 2026-10-11

### Changed
- testcase-generator：`codebase-doctor` の入ったプラグインの名前を devtools から repo-setup に直した

## [0.1.3] - 2026-10-10

### Changed
- testcase-generator：codebase-doctor が devtools プラグインのスキルだと書き添えた

## [0.1.2] - 2026-10-10

### Changed
- testcase-generator：eval の入力から私的なプロジェクト名・関数名を外し、`<your-project>` で当てはめる形にした

## [0.1.1] - 2026-10-06

### Fixed
- full-test-gate：`base` を設定していないときの比較先を `origin/main` 固定から既定ブランチにした。origin に問い合わせ、繋がらなければ手元の origin/HEAD、それも無ければ `origin/main`（無くて `origin/master` があればそちら。guards と同じ）。通知と止めるときのメッセージも、その比較先の名前を出す
- full-test-gate：origin が既定ブランチを変えて手元に `origin/<既定>` がまだ無いときは1回だけ取ってくる（5 秒で打ち切る。取れなければ手元の origin/HEAD を使う）。比較できないとき（ref が無いなど）を「変更 0 件」と取り違えず、`status` と開始時の通知でそう伝える。`run` は比較先が読めなければ記録しない
- full-test-gate：`git fetch` に渡すブランチ名の前に `--` を置き、`-` で始まる名前がオプションとして読まれないようにした

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `testcase-generator` と `testcase-lint`、guards プラグインから `full-test-gate` を移した（中身は変えていない）
