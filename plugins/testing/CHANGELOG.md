# Changelog

Change history of the testing plugin. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.6.1] - 2026-11-26

### Fixed
- full-test-gate reads the local `origin/HEAD` without a network call only while origin has confirmed it and the branch it names has not moved since (`<git common dir>/full-test-gate-origin-head` holds the name and commit). After a fetch moves that branch, for example a branch pushed under the old default's name once the default was renamed and the old branch deleted on origin, the next call asks origin once, so the pushed branch no longer supplies the config. When origin cannot be reached then, the local answer is kept. The first call after this update asks origin once per clone, and so does the first call after each fetch that moves the default branch (one `ls-remote`, about half a second against GitHub); a locally set `origin/HEAD` is reset to origin's answer whenever origin is asked; within an hour of a failed network attempt by the same check origin is not asked and the local answer is kept (#86).
- full-test-gate: a fetched tag or branch named `origin/<default>` no longer hides a valid `origin/HEAD`: `symbolic-ref` is read in full and `refs/remotes/origin/` stripped, instead of `--short`, which printed `remotes/origin/<default>` and made every call ask origin (#86).
- full-test-gate compares, records and measures against `refs/remotes/origin/<default>` (or `refs/remotes/<base>`) when that ref exists, so a tag named `origin/main` (git looks up tags before remote-tracking refs) no longer stands in for the comparison base (#86).
- full-test-gate: in a partial clone (`--filter=blob:none`) whose `.claude/full-test.json` blob is not local, the blob is fetched with a 5-second limit and a failure is cached for an hour like a failed default-branch lookup, so later calls report it unreadable without touching the network instead of refetching on every call (#86).

## [0.6.0] - 2026-11-20

### Changed
- full-test-gate keeps its records in `${CLAUDE_PLUGIN_DATA}/full-test/` (`FULL_TEST_STATE_DIR` still overrides; without the variable, `~/.claude/state/testing/full-test/`). The first run after the update copies `~/.claude/state/full-test/` there once and leaves it as the backup, and the `run` command the hook prints starts with `CLAUDE_PLUGIN_DATA=...` so a run from Bash records where the hook reads (#83).
- `full-test-gate.py run|status` run from Bash without this plugin's `CLAUDE_PLUGIN_DATA` say on stderr that they are not using the hook's records (#83).
- testcase-generator names where the test cases go: next to the repo's existing test-case files, else `docs/testcases/<topic>.md`, or the session scratchpad when they are only to be read (#83).

## [0.5.0] - 2026-11-17

### Changed
- full-test-gate reads `.claude/full-test.json` from the default branch (`origin/<default>`), not the working tree, so a branch can no longer change the `command` that records a pass or drop a `gate` regex that blocks its own release. A repo whose default branch has no config is not opted in. Without an `origin` remote the working tree is read (with a note on stderr). The default branch is the local `origin/HEAD` when the ref it names exists locally; otherwise (none, or dangling after a prune) origin is asked once (5 s, no prompt) and a success is kept as the local `origin/HEAD`, while a failure is kept for an hour so the hook does not wait on every call. `origin/main` / `origin/master` is never guessed. Git variables that select a repository (`GIT_DIR` and the like) are ignored; when the default branch cannot be told, the hook neither gates nor records (stderr says so). The config source and the comparison base use the same default branch, and the test command runs with the same git environment. A config that is on the default branch but cannot be read (a partial clone offline, say) is not gated, with a note on stderr. A missing `origin/<default>` is fetched once into that ref (#77).

### Added
- `full-test-gate.py run --working-tree` runs the working tree's config, to try a new one before merging it. It never records a pass.
- `tests/` with a regression test for full-test-gate (run by CI through `tests/run-all.sh`).

## [0.4.0] - 2026-11-17

### Added
- testcase-generator: a section "Beyond example cases" with property tests (round-trip, invariant, idempotency, equivalence; fast-check, Hypothesis, proptest; when to propose them), differential tests for migrations (same inputs through old and new, normalized differences, a list of approved differences), and a test-cost policy (flaky tests train reruns, slow tests get run less; propose deterministic tests and mark heavy ones "run before commit / before PR"). The idempotency perspective in `perspectives-common.md` points to it.

## [0.3.1] - 2026-10-13

### Removed
- testcase-generator: the eval set (`evals/`) is no longer shipped. The maintainers keep it locally.

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
