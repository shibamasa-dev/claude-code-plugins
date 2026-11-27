# Changelog

Change history of the repo-setup plugin (named devtools up to 0.2.2). Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.8.0] - 2026-11-27

### Added
- python-venv: a skill for where a Python venv goes and how to clean venvs up. One question decides the place (will a second repo or a worktree use it? yes → a shared venv per purpose, no → `<repo>/.venv`); it covers the three layers (project, shared, tool-managed), checking a shared venv for conflicts with `uv pip install --dry-run`, never running `uv pip sync` / `--exact` / `uninstall` on one, keeping source clones apart from venvs, and freezing with `uv pip freeze` before deleting. No hook comes with it.
- python-venv: `scripts/venv_inventory.py`, a read-only inventory of every `pyvenv.cfg` under the given roots (default: the shared venv dir and `~`) with size, created and last-change times and whether a dependency file sits next to it. It flags a venv as likely dead when it stopped changing within minutes of creation and has not changed for days (`--stall-minutes`, `--stale-days`), and prints a table or `--json`. A venv with a part it cannot read is marked incomplete and never flagged dead.
- `userConfig.shared_venv_dir` (default `~/.venvs`): where shared venvs go.
- codebase-doctor: the Boundaries table points at python-venv for placing and cleaning up venvs.

## [0.7.0] - 2026-11-20

### Changed
- codebase-doctor writes its report to `.context/repo-setup/doctor/` (was `.context/doctor/`) and first adds `.context/` to `.git/info/exclude`, so the report stays out of git (#83).

## [0.6.0] - 2026-11-17

### Added
- codebase-doctor: project start. In a repo whose tracked files are only documentation and repo metadata, an interactive run asks up to four questions (what the project is, where it runs, who works on it, hard constraints), skipping any the request already answers, then proposes a stack (language, package manager, framework, test runner, lint/format, CI, hosting) with one reason per row. After the user adopts it, the skill writes a 13–15 line "Decided setup" section between `<!-- codebase-doctor:decided-setup -->` markers in CLAUDE.md, creating the file if needed and appending without changing any existing byte. A run that cannot ask (subagent, headless) writes nothing and says the questions were skipped. On later runs, each line that a manifest or config file now states in full is proposed for removal in one grouped proposal; a line that contradicts the repo is kept and reported; free text inside the markers is never touched. The rules live in the new `references/decided-setup.md`.
- codebase-doctor: Check 16 checks that the test runner's watch mode is off by default.

### Changed
- codebase-doctor: Check 16's fix proposes the tools the Decided setup section names (or tools matching the detected stack), in the order hygiene files → linter → formatter → test runner → CI, per area (a remaining section line wins; otherwise what the repo's files point to, else the detected stack), instead of deferring to a project-local setup command. Manifests are found anywhere in the repo, not only at the root. Check 7 rates a missing manifest SKIP for stacks that have none (shell, Makefile, Terraform). The Boundaries table names `context-diet`, `full-test-gate` and `repo-structure-guard`.

## [0.5.1] - 2026-11-17

### Changed
- verification-skill-builder: for a UI, Evidence keeps a screenshot at the checked step, and a failure carries the trace of steps up to it with what was on screen. The feature map is stated as the pass / fail rubric of a run (a feature with an unverified journey is reported as unverified, and expected results are checked against the README, docs or spec where they cover them), and its template gains a keyboard-shortcut line for apps that have shortcuts. The proof step now runs the finished skill several times in a row and records the duration and pass or fail result of each run; a run that passes only sometimes is a defect to fix before hand-over. A new step 6 says to remove or rename a feature's map row and verification step when the feature is removed or renamed.

## [0.5.0] - 2026-10-30

### Added
- verification-skill-builder: writes a project's own `.claude/skills/verify-<app>/` skill that drives the real app the way users do. The generated skill has a Launch that isolates the run (own run directory, production tokens unset, sending or secret-reading commands replaced by logging stand-ins), a read-only Doctor that refuses unsafe runs, a Drive script of real commands, Evidence that observes what a dry-run actually did instead of trusting its name, and a Cleanup that stops only what the run started, keeps the evidence and fails when production state changed. It also seeds a feature map with fixed headings (action → command → observed result, Gotchas), leaves journeys that need credentials or production services as unverified, and is run end-to-end once before hand-over. It builds one only where the app has several commands run in order.
- codebase-doctor: Check 17, "Real-app verification path". Presence only: PASS with a `verify-*` skill and its `features/README.md`, WARN without the map, FAIL without the skill; SKIP in the `setup` phase, for repos with nothing a user runs, or when CLAUDE.md records that none is needed. Weighted in the `build` and `test` phases. The fix proposes verification-skill-builder.

## [0.4.2] - 2026-10-13

### Removed
- codebase-doctor and remote-setup: the eval sets (`evals/`) are no longer shipped. The maintainers keep them locally.

## [0.4.1] - 2026-10-12

### Changed
- remote-setup: the skill description is written on one line (it was a `>-` block). The text is the same; the repo's check measures descriptions only on one line.

## [0.4.0] - 2026-10-11

### Changed
- Messages, skill bodies, references, comments and tests are now in English. Japanese stays only in the skill descriptions' trigger phrases, in data the features need (patterns that match Japanese text, fixtures for Japanese input) and in `README.ja.md`.
- remote-setup: the generated `scripts/remote-setup/*.sh` templates and the messages `setup.sh` prints into the session context (`[remote-setup] ...`) are now in English. Re-running `scaffold.py` overwrites an existing `setup.sh` with the English version; existing `steps.sh` / `environment-setup.sh` are kept as they are
- codebase-doctor: refers to the section of testing's `perspectives-common.md` as section 7, "Project-specific perspectives" (the heading the English testing plugin uses)

## [0.3.0] - 2026-10-11

### Changed
- **プラグインの名前を devtools から repo-setup に変えた。** 開発のどこで使うか（リポの立ち上げ）が名前から分かるようにするため。devtools を入れていたら外して repo-setup を入れる

### Removed
- 使用枠を書き出す mod（`rate-limits`）を workflow プラグインへ移した。書き出し先と形式は変わらない。引き続き使うには workflow を入れる

## [0.2.2] - 2026-10-10

### Changed
- codebase-doctor：testcase-generator が testing プラグインのスキルだと書き添えた

## [0.2.1] - 2026-10-10

### Changed
- remote-setup：ローカルの venv 運用への言及を外し、eval の入力を入れた人が用意できるリポの記述にした

## [0.2.0] - 2026-10-09

### Added
- 使用枠（rate limits）を `/tmp/claude-<uid>/rate-limits.json` へ書き出す mod（`hooks/rate-limits.ts`）。`session.start` と `session.measure` で `five_hour` / `seven_day` の `used_percentage`・`resets_at`・`seen_at` を書く。並列セッションの古い値ではなるべく上書きせず（ロックは無いベストエフォート）、本人専用ディレクトリ内で一時ファイル→`mv -f` で書く

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `codebase-doctor`・`remote-setup` を移した。`codebase-doctor` は testing プラグインの `testcase-generator` を名前で参照し、testing が無ければテスト設計の点検（Check 6b）を SKIP にする
