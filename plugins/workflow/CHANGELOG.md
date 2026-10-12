# Changelog

Changes to the workflow plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are plugin.json's `version`.

## [0.6.0] - 2026-10-13

### Added
- choice-board: a skill for deciding on 10 or more items. Each item becomes a row on a board Artifact (one per project) with its options, the recommended one marked, and a memo; choices are saved to the Artifact database and read back with `ArtifactData`. Template in `assets/board.html`, design rules in `references/design.md`.

## [0.5.0] - 2026-10-12

### Removed
- The top-level `bin/` directory (`handoff`, `issue-writeback`, `runbook`), so the plugin can be added to a claude.ai marketplace. The bare `handoff` / `issue-writeback` / `runbook` commands are no longer on PATH.

### Changed
- The CLIs run as `python3 "<plugin root>/hooks/<name>.py" <subcommand>`. Hook messages (the handoff SessionStart injection, the issue-writeback and runbook Stop messages) print that command with the absolute path; skills and READMEs use `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py" ...`.
- tests: `test-handoff.sh` and `test-issue-writeback.sh` run the printed `consume` / `dismiss` command as printed; `test-runbook.sh` checks that the Stop message names the hook script.

## [0.4.1] - 2026-10-11

### Fixed
- context-diet: the inventory proposal (criteria.md rule 11) now groups only connectors and personal skills, matching SKILL.md; plugin and account-side skills are left out because `skillOverrides` has no effect on them (a plugin can be disabled through `enabledPlugins` as a separate topic; account-side skills have no known lever).
- context-diet: the docs now give the real default for the index average line length (120 chars; they said 100).
- context-diet: `measure.py`'s `tokens_estimate` divides by 4 when more than 70% of the always-loaded bytes are ASCII, else by 3 (it always divided by 3, which assumed Japanese text).
- weekly-orchestrator-base: the batch-table step now says to fill in Run via and Status before sending, then send (it contradicted itself), and to set Status back if sending fails.
- dev-process: `agent-review.sh` runs `codex exec '/review'` without a hardcoded Japanese output directive.
- dev-process: `review-and-fix` explains why `agent-review.sh` needs sandbox access to `~/.codex` (the codex CLI writes session state there) and prefers allowing only that directory via `/sandbox` over `dangerouslyDisableSandbox: true`.
- tests: `test-knowledge-freshness.sh` prints its exit-code, stderr and payload checks as verdict rows that `run-all.sh` counts, so a wrong exit code is now a mismatch, and its fixture lives in a fresh `mktemp -d` directory so concurrent runs don't collide. `run-all.sh` exits non-zero on any mismatch.

## [0.4.0] - 2026-10-11

### Changed
- Messages, skill bodies, references, comments and tests are now in English. Japanese stays only in the skill descriptions' trigger phrases, in data the features need (patterns that match Japanese text, fixtures for Japanese input) and in `README.ja.md`.
- The issue section written at close / before merging a `Closes` PR is now `## Result` (was `## 結果`). dev-flow-gate still accepts `## 結果` and `## Results`.
- The recurring-task handoff section is now `## Notes for next time` (was `## 次回への引き継ぎ`). dev-flow-gate accepts both (it now also counts `## Notes for next time`).
- The PR-body section where Claude records its own review is now `## Review (Claude)` (was `## レビュー（Claude）`). No hook reads it; dev-flow and pr-review-triage still count the old heading in older PRs.
- The PR-body section for out-of-scope findings is now `## Out-of-scope notes` (was `## スコープ外の気づき`). No hook reads it; pr-review-triage notes the old name.
- weekly-orchestrator-base: the `## Result` first-line markers are now `**Cutoff**:` / `**Submitted**:` / `**Tally start**:` (were `**締め**:` / `**提出**:` / `**集計起点**:`), the plan status values are `Draft` / `Confirmed YYYY-MM-DD` (were `未確定` / `確定`), the batch Status values are `Not started` / `Running` / `PR #N` / `Done` / `Blocked (reason)` (were `未着手` / `実行中` / `完了` / `止まっている`), and the plan-section template headings and columns are English. The skill notes the old Japanese values for older cycle issues.
- runbook: new `runbook.md` files get English headings (`## Goal`, `## Prerequisites and inputs`, `## Steps`, `## Branches and pitfalls`, `## Stop points`, `## Verification`, `## Recording`); existing runbooks are untouched. A masked `javascript:`/`data:` URL in `steps.jsonl` is now written as `<N chars>` (was `<N文字>`).
- pr-review-triage: `classify.sh` reason lines are English (e.g. `- Non-document files: ...`, `- Changed lines: 262 > 200`), and `run_evals.sh` prints `==== PASS N / FAIL N ====`.
- handoff: the injected and printed labels are English (`entry:` / `state:` / `next:`); the state file format is unchanged.
- context-diet: `measure.py` breach strings read `<key>: N entries` (was `N件`).
- tests: rows read `(expect X)` and `tests/run-all.sh` ends with `==== N as expected / N mismatches ====` (was `==== 期待どおり N 件 / 食い違い N 件 ====`).

## [0.3.0] - 2026-10-11

### Added
- review プラグイン（0.6.1）を統合した。`pr-review-triage` スキル・`dev-process` コマンド（`/workflow:dev-process:review-and-fix`）・テスト（`tests/test-detect-bots.sh`）と、userConfig `review_heavy`・`review_light`・`review_auto`・`rereview_threshold` をそのまま移した。dev-flow の 5・6 段と同じプラグインで、片方だけ入れて流れが途切れることが無くなる。review を入れていたら外し、設定を workflow の同じキーに入れ直す。review の変更履歴は review を消す前の git の履歴（`plugins/review/CHANGELOG.md`）にある
- 使用枠（5時間・週）を `/tmp/claude-<uid>/rate-limits.json` に書き出す mod（`hooks/rate-limits.ts`）を devtools（今の repo-setup）から移した。書き出し先と形式は変えていない

### Changed
- dev-flow・dev-flow-gate・session-wrap・weekly-orchestrator-base：「review プラグインの pr-review-triage」を同じプラグインのスキルとして書き直した

## [0.2.3] - 2026-10-10

### Changed
- dev-flow：軽い PR の振り分けとマージ提案の条件を、light のレビュー役（`review-light:`）に `claude` が含まれれば `## レビュー（Claude）` がある、ツールが含まれればそのツールすべての結果が揃った（両方なら両方）、にした（review 0.6.1 の `review-light: claude, codex` に合わせた）

## [0.2.2] - 2026-10-10

### Changed
- dev-flow：レビューツールの決め方を review 0.6.0 の名前（`review-heavy:`・`review-light:`・`review-auto:` 行、userConfig `review_heavy`・`review_light`・`review_auto`）にした。4 段（PR を作る）に、ツールの自動レビューが ON のリポ（`review-auto: on`）では PR を作る前に振り分けて、軽い PR は `review:light` ラベルを付けて `gh pr create --label` で作ることを足した。軽い PR のレビューとマージ提案の条件は、light のレビュー役（`review-light:`）が `claude` なら `## レビュー（Claude）`、ツールならそのツールすべての結果、で分けた
- `none`（`review-light: none`・`review-heavy: none`）のときは Claude がレビューし、マージ提案の条件も `## レビュー（Claude）` で判定する（light → heavy に変わった PR も同じ）

## [0.2.1] - 2026-10-10

### Changed
- dev-flow：4 段（PR を作る）に PR の粒度の目安を足した。1 つの issue につき開いている PR は 1 本（続きは追加 push。例外は前の PR が閉じた後と `gh-stack` の層）、大きさは 500〜800 行が目安（層に分けるのは今の変更に依存する境目があるときだけ）。レビューの結果が返った後に指摘への対応以外の新しい作業を足したら、その push でもう一度レビューを頼む

## [0.2.0] - 2026-10-10

### Added
- `dev-flow` スキルと `dev-flow-gate` フックを review プラグインから移した。issue-ops と同じプラグインで、依頼から `## 結果` までの流れが揃う。dev-flow-gate の状態は新しい置き場（`${CLAUDE_PLUGIN_DATA}/dev-flow-gate/`）で取り直す

### Changed
- dev-flow：自動マージの判定は既定ブランチの `.claude/dev-flow.json` で行い、作業ブランチの値では決めない（有効にする PR 自身を自動マージしないため）。自動マージの実行の場所はリポ側の文書に定めがあればそれに従う

## [0.1.11] - 2026-10-10

### Changed
- session-wrap・weekly-orchestrator-base：pr-review-triage（review）・bash-guard（guards）が別のプラグインだと書き添え、guards が無くても push 前の確認が読めるようにした

## [0.1.10] - 2026-10-10

### Changed
- issue-ops・session-wrap・weekly-orchestrator-base・context-diet：本文から日付つきの決定・実例・実測と、作った環境に固有の名前（私的スキル名・サービス名・ファイル名）を外した。別セッションの起動は、特定のスキル名ではなく「別のセッションを待機状態で起動できるスキルや仕組み（環境にあれば）」と機能で書いた

## [0.1.9] - 2026-10-09

### Changed
- session-wrap・weekly-orchestrator-base・issue-writeback：レビュー待ちの参照先を、review プラグインで統合された `pr-review-triage` にした

## [0.1.8] - 2026-10-06

### Changed
- issue-ops：アーキレビュー・ゲートの判定と PR 本文の欄は review プラグインの `dev-flow` に移し、ここには issue 側の操作だけ残した。`## 結果` は「`Closes` を書く前」ではなく「`Closes` の PR をマージする前」に書く、に揃えた。PR の突き合わせと body の読み方をコネクタのツールで書いた

## [0.1.7] - 2026-10-06

### Removed
- `pr-review-wait`・`pr-rereview`・コマンド `review-and-fix` を review プラグインへ、`testcase-generator`・`testcase-lint` を testing プラグインへ、`codebase-doctor`・`remote-setup` を devtools プラグインへ移した。引き続き使うにはそれぞれのプラグインを入れる
- `openapi-to-skills` を削除した（使われていないため）

## [0.1.6] - 2026-10-06

### Fixed
- issue-writeback：PR への読み取り（`gh issue view` に PR 番号を渡した場合など）を issue の書き戻し対象から外す。番号なしやブランチ指定の `gh pr` 書き込みも、出力か `gh pr view` で PR を特定して追跡する

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
