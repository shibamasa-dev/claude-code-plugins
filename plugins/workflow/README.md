# workflow

English | [日本語](README.ja.md)

Skills and hooks that turn the path from request to merge (including routing and waiting for PR reviews), issue hygiene and session handling into a repeatable routine. Test design lives in [testing](../testing/README.md); repo bootstrapping lives in [repo-setup](../repo-setup/README.md).

If you used the former `review` plugin, uninstall it and move its settings to the keys under [Configuration](#configuration-userconfig) below. The `pr-review-triage` skill, the `dev-process` command and the review settings now live here.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install workflow@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `dev-flow` | The entry point of the development flow, for issues and verbal requests alike. Holds the order and the commitments: deciding whether a change is structural and needs an architecture review → implementation and self-review → PR → waiting for reviews → `## Result` → merge. Delegates the review stage to `pr-review-triage`. Auto-merge is enabled per repo in `.claude/dev-flow.json` |
| `pr-review-triage` | Right after opening a PR or pushing to one, routes the review by the size of the diff. Light PRs (docs only, or up to 200 lines) follow `review_light`: with the default `claude`, Claude reviews and writes the result in the PR body, then waits only for CI; list tool ids (alone or next to `claude`) to also wait for those tools. Heavy PRs are sent to review tools (CodeRabbit, Codex, …) through a connector — or, in repos where the tool's auto review is on, not requested, and only light PRs are excluded from auto review with the `review:light` label — then the results are awaited, assessed and addressed in a response table with a severity column (Important / Nit / Pre-existing). Also decides whether to request a re-review; when none is requested, rereads the fix commits' diff and records the checked commit in the PR body |
| `issue-ops` | Conventions from filing an issue to closing it (how to write the body, writing results back before closing) |
| `session-wrap` | Checks for leftovers before closing a session and leaves a handoff for the next one |
| `context-diet` | Measures and trims the context loaded at every session start |
| `weekly-orchestrator-base` | A base for a repository's one long-lived orchestrator session (title starting with `🎯 <repo>`, pinned and used every day): runs a weekly plan → delegate → check → close loop, sends PR work to child sessions and read-only checks to subagents, and keeps its state in the cycle issue so a manual `/clear` loses nothing. Has defaults (weekly cycle, issue title) for repos without their own orchestrator skill |
| `choice-board` | When you have to decide something for each of 10 or more items, puts them on a board page instead of in chat: one row per item with its options (the recommended one marked) and a memo, saved to the Artifact database so Claude reads the choices back. One board per project, reused across rounds. Needs the Artifact tools (Claude Code connected to claude.ai) |

## Hooks

| Hook | When | What it does |
|---|---|---|
| handoff | Session start | Injects the "next entry point" left by the previous session. Write an entry with `CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" write --entry <owner>/<repo>#<n> --state "..." --next "..."` and clear one with `... consume --entry <entry>`; the injected text prints the exact command |
| issue-writeback | Session start, prompt submit, stop, session end, after issue operations | Reminds you if decisions were not written back to an issue you read |
| runbook | After browser or computer-use actions, on stop, at session start | Records browser and screen-operation steps; on the first one, says to start a GIF recording (Chrome) or note key steps (tools that cannot record); stops if you forgot to write the runbook |
| orchestrator-report | After creating or updating a PR, or writing to an issue (connector or `gh`) | If exactly one running session in the repository written to (its folder's `origin`; worktrees included) has a title starting with `🎯` and it is not this session, tells Claude to send it a one-line report with SendMessage. Once per PR / issue per session; skipped in cloud and Claude Projects sessions |
| knowledge-freshness | Session start | Reports knowledge files past their review date in one line |
| artifact-ledger | After Artifact | Records published Artifacts in the project's `.artifacts/` (see [Artifact ledger](#artifact-ledger)) |
| dev-flow-gate | Before creating a PR | Blocks if the body lacks `Closes #N` / `Refs #N` (`Refs: none (verbal request)` for requests without an issue) or the `Arch-Review:` field |
| | After creating a PR | Tells Claude the next stage (wait for reviews and CI) |
| | Before ending a turn | Blocks once per PR if waiting (a PR event subscription or a Monitor) has not started for a PR created in this session |
| | Before a merge | Blocks if there is no record that the `## Result` section (the older `## 結果` also counts) of the issue the PR closes was written or read and confirmed |
| commit-gate | When a verifier skill runs (typed `/code-review`, or through the Skill tool), at the end of that turn, before and after `git commit` | Off by default. When on, checks that a review or verification ran on the tree being committed and that the commit message's `Verification:` trailer says so. `observe` only says what it would have done; `enforce` blocks |
| pr-checks (part of dev-flow-gate) | Before creating a PR, after the body check passed | Off by default. When on, looks up whether the repo's check command (`prChecks`) passed locally on the tree being proposed, recorded by `checks.py run`. `observe` only logs and says what it would have done; `enforce` blocks |

dev-flow-gate watches both the GitHub connector (`create_pull_request`, `merge_pull_request`, `enable_pr_auto_merge`, `issue_read`, `issue_write`) and `gh`. It never queries GitHub itself; it decides only from tool calls made in the session (merging a PR created in another session isn't blocked, it just asks Claude to check). State lives in `${CLAUDE_PLUGIN_DATA}/dev-flow-gate/<session_id>.json`, and files older than 30 days are removed at session start.

commit-gate:

- **Evidence**: a verifier is a skill whose name matches `commit_gate_verifiers` (default `^(code-review|(.+:)?verify-.+|coderabbit:code-review)$`). It is seen when typed (`/code-review`, through the `UserPromptExpansion` event) or when Claude calls it with the Skill tool. It counts as fresh until the end of the turn it ran in, so fixes made in that turn are covered; at the end of the turn it is tied to a fingerprint of the tree. After that it counts, for any session, only while the fingerprint is unchanged. Once the tree changes it is stale for the session that ran it; for other sessions it is simply missing.
- **Fingerprint**: the working tree's change against `merge-base(HEAD, origin/HEAD)`, untracked files included (`git diff --raw` hashed, through a temporary index and object directory, so nothing is written to the repo). Committing part of the change, pushing, or a clean rebase keeps it; any edit, by any tool, changes it. Without a merge-base it is the tree hash.
- **Stamp**: end each commit message with `Verification: <kinds> — <names>` (for example `Verification: review — code-review`; kinds are `review` and `verify`) or `Verification: none — <reason>`. The gate checks named verifiers against its record. Find unverified commits with `git log origin/main --grep='^Verification: none'`.
- **At `git commit`** (`enforce`): fresh evidence and a matching trailer pass; `none — <reason>` passes and is logged as explained; anything else is blocked: no evidence, stale evidence, a trailer naming a verifier with no record, a missing trailer (the block names the line to add), a message that cannot be read (a variable, the editor), or a staged version of a file that differs from the working tree that was verified (unless the commit takes that file from the working tree itself: `-a`, or the path named with or without `-i`; paths given through `--pathspec-from-file` are not read, so every file is checked, and so are named paths next to a quoted or expanded word that looks like a redirection (`'>'`) or an abbreviated long option (`--mess`), where the words cannot be told apart. Unquoted redirections (`2>&1 | tail -3`, `>/dev/null`) are not arguments and are ignored; a file removed with `git rm --cached` but still in the working tree counts as differing, unless git ignores it (then it is left out of the verified tree too); a submodule whose only change is a dirty worktree does not count). After two blocks in a session the next commit is let through (logged as released) and the count resets. `observe` never blocks: it tells Claude what it would have done, runs the same count, and allows stale evidence with a note to mark the trailer `(stale)`.
- **Log**: every decision goes to `${CLAUDE_PLUGIN_DATA}/commit-gate/log.jsonl` with the session, repo, branch and fingerprint; after a commit (seen as HEAD moving, so `git commit -q` counts too), a `committed` line records its sha and whether its stamp is backed by the record. An unexpected error in the hook is logged as `error` (the commit is then not checked); on first use, with the gate on, the state directory is created for it (never in `off`). A command that mentions `git commit` but cannot be parsed (an unbalanced quote) is not checked; it is logged as `unparsed` and Claude is told. `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/commit_gate.py" report` lists the would-be blocks (`--all` lists everything). Evidence and the block count live in `${CLAUDE_PLUGIN_DATA}/commit-gate/` (`~/.claude/state/workflow/commit-gate/` when that variable is not set); files older than 30 days are removed at session start.
- **Cost**: in `off` it writes nothing, says nothing and makes no network call; what still runs is local git. Before each Bash call the hook exits at once unless the command contains both `git` and `commit`; then two to four local git reads find the repo and its file. After each Bash call that reports `duration_ms` it runs one `git log -g -1` (about 10 ms; no file written). A typed command or a Skill call reads the repo file the same way. Session start behaves as in Limitations. When on, the fingerprint is computed at each commit and at the end of a turn in which a verifier ran (about 0.3 s on a 12,000-file repo).

pr-checks (local checks before the PR):

- **What it asks**: when a PR is created (`gh pr create` or the connector's `create_pull_request`), is there a recorded pass of the repo's check command for this tree? The command is `prChecks` in `.claude/verification.json` on the default branch. The tree is identified by the same fingerprint commit-gate uses (the working tree's change against `merge-base(HEAD, origin/HEAD)`, untracked files included), so any edit after the run makes the pass no longer apply, and a pass under an older `prChecks` command does not count. A recorded pass is trusted as it is: the gate looks it up and never runs the checks itself.
- **Recording a pass**: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/checks.py" run` runs the default branch's command from the repo's top level and records a pass when it exits 0 and the fingerprint is the same before and after the run (a command that edits the tree, or leaves an output file that is not ignored, records nothing and exits 3). `run --working-tree` runs the working tree's command instead, to try a new config, and never records. Passes are kept in the repo, in `<git common dir>/workflow-pr-checks.json` (the newest 50), so worktrees and parallel sessions share them: the same tree gives the same result. `${CLAUDE_PLUGIN_ROOT}` is the plugin's install directory and is not set in a plain shell: write the path out there (the gate's message prints the command with the path filled in).
- **Modes**: `off` (the default), `observe`, `enforce`; `prChecksGate` in the repo file, else userConfig `pr_checks_gate`.
  - `off`: at a PR creation, after dev-flow-gate's own body check passed, it reads the repo's config with two to four local git reads and returns. It writes nothing, says nothing and denies nothing; there is no network call and nothing runs on any other tool call.
  - `observe`: never blocks. One line per PR creation goes to the log, and Claude is told when there is no pass.
  - `enforce`: denies a PR creation with no recorded pass, unless the PR body has `Local-Checks: none — <reason>` (logged as `explained`). After two denials in a session the next creation is let through (logged as `released`).
- **Never denied when it is not certain**: it denies only when the PR's repo is the origin of the directory the PR is created from and its head is the branch checked out there. A directory that cannot be told from the command (`cd "$VAR" && gh pr create`), `-R` / `GH_REPO` / connector `owner` and `repo` naming another repo, `--head` naming another branch, a detached HEAD, an unknown default branch, a gate that is on with no `prChecks` command, and a fingerprint that cannot be computed, a git or gh command earlier in the same call that may move the branch, the tree or gh's default repo (`git switch`, `gh pr checkout`, `gh repo set-default`), and `gh repo set-default` naming a repo other than `origin` are each said and logged (`unresolved`, `nogate`, `nocommand`, `unchecked`) in `observe` and `enforce`, never denied; in `off` they are silent, like everything else.
- **Log**: `<git common dir>/workflow-pr-checks.log.jsonl`, next to the pass file and per repo (for the same reason: `report` is started from Bash, where `CLAUDE_PLUGIN_DATA` is not this plugin's). One line per PR creation with the session, repo, branch, head commit (`pr_head`), fingerprint, `had_pass`, whether the tree had uncommitted changes (`dirty`) and the decision. `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/checks.py" report`, run inside the repo, lists the creations that had no pass (`--all` lists everything). When the log cannot be written, the decision is the same as with it (a missing pass still denies in `enforce`) and Claude is told that the line is lost. When the hook fails while deciding, the PR is not denied, Claude is told, and an `error` line is logged. Only the per-session denial count is under `${CLAUDE_PLUGIN_DATA}/checks/blocks/` (`~/.claude/state/workflow/checks/blocks/` when that variable is not set).
- **The PR body file**: an untracked file that the `gh pr create` call itself names as its body (`--body-file` / `-F`) is left out of the fingerprint, so writing the body inside the repo after the checks ran does not undo the pass. For a body file that was already there when the checks ran, `run` also records, for each untracked file (up to 10), the fingerprint with that one file left out, so editing the body afterwards (after dev-flow-gate rejected it, say) does not undo the pass either. The file is matched as the same file on disk, so another spelling on a case-insensitive filesystem or a symlink to it works. Nothing else is exempt: any other new, changed or deleted untracked file that is not ignored counts as a change (ignore it, or run the checks again). A path outside the repo avoids the question.
- **Cost**: in `off`, two to four local git reads on a PR creation (about 40 ms in one measurement) and nothing on any other command; no network call in any mode.

orchestrator-report keeps the PRs and issues it already asked about in `${CLAUDE_PLUGIN_DATA}/orchestrator-report/<session_id>.json` (files older than 30 days are removed when it writes).

## Mods

| Mod | What it does |
|---|---|
| `rate-limits` | Writes usage limits (5-hour and weekly) to `/tmp/claude-<uid>/rate-limits.json`, where `<uid>` is `id -u`. Lets an external script watch the remaining weekly quota |

The output looks like `{"five_hour": {"used_percentage": 17, "resets_at": 1791553800, "seen_at": 1791552278}, "seven_day": {...}}` (`resets_at` and `seen_at` are epoch seconds). For each window it keeps the entry with the larger `resets_at`, or the larger `used_percentage` on a tie. This is best effort: there's no inter-process lock, so parallel sessions writing at almost the same time can briefly roll back to an older value, which is fixed the next time usage changes. Nothing is written when values don't change. The output directory is private to you (mode 700) and is created if missing; if it is a link, owned by someone else, or not 700, nothing is written. The file is written to a temporary file and replaced with `mv -f` (nothing is written on failure). The mod runs only in the Claude Code CLI (it uses `$.process`).

## Configuration (userConfig)

| Key | Default | Use |
|---|---|---|
| `review_heavy` | empty | Review tools for heavy PRs (comma-separated, e.g. `coderabbit,codex`; `none` for no tool). If neither a repo line nor this setting exists, `pr-review-triage` asks you |
| `review_light` | `claude` | What reviews light PRs. `claude` means Claude reviews. Listing tool ids treats light PRs like heavy ones (no label) |
| `review_auto` | `off` | Whether the tool's auto review is on (`on` / `off`). See "Keeping auto review on" below |
| `rereview_threshold` | 3 | Request a re-review only when you fixed at least this many severe findings (Critical / P1 or equivalent) |
| `freshness_targets` | `~/.claude/rules:*.md,~/.claude/reference:*.md,~/.claude/skills:*/SKILL.md` | Directories the knowledge-freshness hook checks: comma-separated `<dir>:<glob>` pairs, `~` expanded, `**` in the glob is recursive, a directory name cannot contain a comma. Files whose `review_after` has passed, or that have no `last_reviewed`, are listed at session start. Empty means the default |
| `commit_gate` | `off` | The commit gate's mode: `off`, `observe` or `enforce` (any other value is `off`). A repo's `.claude/verification.json` overrides it |
| `commit_gate_verifiers` | empty | A regex of skill names that count as verification. Empty means `^(code-review\|(.+:)?verify-.+\|coderabbit:code-review)$` |
| `pr_checks_gate` | `off` | The mode of the local-checks test at PR creation: `off`, `observe` or `enforce` (any other value is `off`). A repo's `.claude/verification.json` (`prChecksGate`) overrides it |

Available tool ids are the file names in `skills/pr-review-triage/references/tools/` (`codex`, `coderabbit`, `copilot`, `gemini`, `cursor-bugbot`).

To override per repo, add lines to the repo's CLAUDE.md (or AGENTS.md). Lines take precedence over userConfig. They are read from the default branch (`origin/<default>`), not the working tree, so a line added or changed in a PR takes effect once that PR is merged and your local `origin/<default>` is fetched (a repo without an `origin` remote reads the working tree). `review-notes:` is free text describing what reviewers should focus on; it goes into the request and into Claude's review (it isn't used for routing):

```
review-heavy: coderabbit, codex
review-light: claude
review-auto: on
review-notes: please look closely at permission changes
```

To set the commit gate per repo, put `.claude/verification.json` on the default branch. It takes precedence over userConfig and, like the `review-*:` lines, is read from `origin/<default>` (through the local `origin/HEAD`), so a branch cannot turn off or loosen the gate it is judged by; a change takes effect once it is merged and fetched. A repo without an `origin` remote reads the working tree:

```json
{"commitGate": "observe", "verifiers": "^(code-review|verify-.+)$"}
```

The same file carries the local checks before a PR, read from the default branch in the same way: `prChecks` is the command `checks.py run` runs (through `sh -c`, from the repo's top level), and `prChecksGate` is the mode. A branch can change neither for itself; to try a new command before it is merged, use `checks.py run --working-tree`, which never records:

```json
{"prChecksGate": "observe", "prChecks": "npm test && npm run lint"}
```

### Keeping auto review on (`review-auto: on`)

Keep the tool's auto review on and exclude only light PRs with a label. A manual `@coderabbitai review` also counts against CodeRabbit's limit, so turning auto review off doesn't save quota. CodeRabbit doesn't count PRs excluded by its auto-review controls (such as labels) against the limit ([rate limits](https://docs.coderabbit.ai/management/rate-limits)).

- Light PRs (with `review-light: claude`) are classified before creation and created with the `review:light` label. Claude reviews them
- Heavy PRs are reviewed automatically by the tool, so no request comment is posted; the results are awaited
- If a push turns a light PR into a heavy one, the label is removed and the tool is asked manually
- Listing tools, as in `review-light: coderabbit, codex`, means light PRs get no label and are treated like heavy ones (this is how you stop using the label)
- Listing `claude` and tools, as in `review-light: claude, codex`, labels light PRs, has Claude review them, and also waits for auto reviews from tools that a label doesn't exclude (such as Codex). Don't list tools that the label excludes (CodeRabbit): their results would never arrive

Configure the tool to skip labeled PRs. For CodeRabbit, in the repo's `.coderabbit.yaml`:

```yaml
reviews:
  auto_review:
    labels: ["!review:light"]
```

A label starting with `!` is a negative match ([configuration](https://docs.coderabbit.ai/reference/configuration)).

**Unverified** (not measured yet):
1. Whether CodeRabbit skips a PR based on a label added at creation time, before its first auto review
2. Whether this setting can be applied organization-wide (otherwise use a per-repo `.coderabbit.yaml`)
3. Whether Codex can be excluded from auto review by a label (if not, Codex runs on light PRs too)

### Where files go

| What | Where | Uninstalling the plugin removes it |
|---|---|---|
| Hook state: handoff entries, issue-writeback, dev-flow-gate, orchestrator-report, commit-gate, the pr-checks denial count | `${CLAUDE_PLUGIN_DATA}/<feature>/` (`~/.claude/plugins/data/<plugin id>/`) | Yes, from the last scope it is installed in, unless you pass `--keep-data` |
| The same state written by a script run without the variable | `~/.claude/state/workflow/<feature>/` | No |
| handoff entries with `HANDOFF_STATE_DIR` set | that directory | No |
| pr-checks passes and their log | `<git common dir>/workflow-pr-checks.json` and `.log.jsonl` | No (they belong to the clone) |
| Runbooks and their raw logs | `RUNBOOK_ROOT`, default `~/.claude/runbooks/` | No (they are your documents) |
| Artifact ledger | `.artifacts/` at the project root (see Storage) | No |
| review-and-fix reviews, fix plans and debug log | `.context/workflow/review/`, `plan/` and `logs/` in the repo; the command adds `.context/` to `.git/info/exclude` | No |
| Usage limits (rate-limits mod) | `/tmp/claude-<uid>/rate-limits.json` | No (temporary) |

```bash
claude plugin uninstall workflow@shibamasa-plugins --keep-data
```

Coming from an older version, the first run copies `~/.claude/state/issue-writeback/` and `~/.claude/state/handoff/` to the new place once and leaves the old directories as a backup; delete them when you no longer need them. dev-flow-gate, orchestrator-report, checks and commit-gate already used `${CLAUDE_PLUGIN_DATA}`; only their place without the variable moved, from `~/.claude/state/<feature>/` to `~/.claude/state/workflow/<feature>/`, and that state is not copied. A command run from Bash that ends up on the `~/.claude/state/workflow/` fallback says so on stderr. Bash does not get `CLAUDE_PLUGIN_DATA`, so the commands the hooks print and the skills give (handoff, issue-writeback, session-wrap's survey) start with `CLAUDE_PLUGIN_DATA=...`; keep that prefix when you run one yourself.

## Commands

- `/workflow:dev-process:review-and-fix` — runs AI review → assessment → fix plan → implementation in one go

## Organization values

Organization values (GitHub org, default repo, Issue Fields, project board) aren't stored in the skills. The skills read an injected text block headed "Organization settings" (or 「組織設定」) from the session context if present, otherwise the project's CLAUDE.md. Internal values are meant to be injected by a separate plugin through a SessionStart hook.

## Storage

| Environment variable | Default | Contents |
|---|---|---|
| `HANDOFF_STATE_DIR` | unset (`${CLAUDE_PLUGIN_DATA}/handoff`) | handoff entry points |
| `RUNBOOK_ROOT` | `~/.claude/runbooks` | runbook raw logs and written runbooks |

### Artifact ledger

The artifact-ledger hook keeps two files in `.artifacts/` at the project root:

- `ledger.jsonl` is the source of truth and is tracked by git. Each publish appends one line (artifact id, URL, title, description, icon, version, repo-relative source path, session id). The icon is the publish's `icon` (or the deprecated `favicon` when only that is passed) and is stored under the key `favicon`; `index.html` shows it in the first column; lines are only appended, never rewritten.
- `index.html` is generated from the ledger (a table of titles, first publish and last update). It is not meant to be tracked: the hook does not edit `.gitignore`, so add `.artifacts/index.html` there. It is rebuilt after each append, and rebuilt from the ledger when it is missing.
- In a worktree the ledger lives under the parent repository's root, so deleting the worktree does not delete it.
- A `list` call never adds artifacts: it appends the response's `updatedAt` only for ids already in the ledger, because the list mixes every project.

The hook prints nothing and always exits 0.

## Limitations

- orchestrator-report finds the orchestrator with `claude agents --json`, which lists only sessions whose process is running. While the orchestrator's process is not running (e.g. after the app restarts, before the session is opened again), no report is requested
- Cloud sessions and Claude Projects sessions do not report to a local orchestrator (they cannot send messages to local sessions)
- The checks that read their config from the default branch (pr-review-triage's `review-*:` lines) defend against what a branch's content can change (committed files, pushed branches). They trust the local git configuration and environment, and origin's default branch is the authority: in a fork workflow that is the fork, not `upstream`.
- When origin's default branch cannot be determined (no usable local `origin/HEAD` and origin unreachable), the check does not run, says so, and asks origin again no sooner than an hour later.
- When `origin/<default>`, or a file on it, cannot be read, the repo's `review-*:` lines are skipped with a note on stderr, and userConfig and then the defaults apply (`review-heavy` has no default, so `detect-bots.sh` exits 4). An `origin/<default>` already fetched is read as it is, even when it is behind origin.
- commit-gate is a nudge against forgetting, not a barrier against a determined author: the default verifier regex accepts any `verify-*` skill, including one added on the branch being committed, and `Verification: none — <reason>` is always accepted. A repo that wants more sets `verifiers` in `.claude/verification.json` on the default branch. Forging evidence locally (piping events into the hook, editing its state files) is outside what it defends against.
- commit-gate reads the repo file through the local `origin/HEAD` only, so the per-call path makes no network call. When `origin/HEAD` is missing, session start asks origin once (at most once an hour per repo) and saves the answer, but only when userConfig turns the gate on or the repo has `.claude/verification.json` at HEAD or in the working tree; it runs git with `GIT_TERMINAL_PROMPT=0` and the user's ssh command (`GIT_SSH_COMMAND`, `core.sshCommand` or `GIT_SSH`) in BatchMode, so it never waits for a password. Until then it does not gate (`git remote set-head origin --auto` also fixes it). A repo that opts in only on a default branch it has not merged locally is not seen until it is merged or the user turns the gate on.
- A `commitGate` value in the repo file that is not `off` / `observe` / `enforce` (a typo such as `"bogus"`, or `true`) is ignored and userConfig applies; with the gate on, each commit logs it as `config_invalid` and says so. With userConfig unset, the gate is then off and says nothing.
- commit-gate cannot tell the target repo of `cd "$VAR" && git commit`, `git -C "$VAR" commit`, `cd - && git commit`, `pushd` without a directory, `popd` past the stack, `GIT_DIR=… git commit` or `git --git-dir=… commit`. They are never judged against the session's directory and never blocked, in any mode (the target may be a repo that does not gate): with the gate on they are logged as `unresolved` and Claude is asked to name the repo (`git -C <path> commit`). `cd ~-` / `cd ~+` are unresolved too. A quoted `"~"` (a directory literally named `~`) is read as the home directory. An `env` option that env does not have makes the target unresolved. `$PWD`, `${PWD}`, `$(pwd)`, `` `pwd` `` and `$(git rev-parse --show-toplevel)` are followed, a `cd` inside `( … )` ends with the subshell, `pushd` / `popd` keep a stack, and `env -C <dir>` runs the commit in `<dir>`.
- commit-gate blocks a commit after `git add -p` (only some hunks staged): the staged and working-tree versions differ, and what was verified is the working tree, not the staged part. Write `Verification: none — <reason>` for such commits.
- `sh -c` / `bash -lc` and the like are read, including `sh -c -- '…'`, up to three levels deep; other shells (`fish -c`, `pwsh -c`) are not.
- A command that cannot be encoded (a lone surrogate in the message) makes the hook fail open: the commit is not checked and an `error` line is logged.
- `--no-all` after `-a`, or a value after an abbreviated long option that reads as `-a` (`--mess -a`), is not read as such: the commit is still treated as staging every tracked file, so the staged-content check is skipped.
- Redirections are marked internally with the word `__SHELL_REDIR__`; a command that types that word itself can make the next word disappear from what the hooks read.
- commit-gate does not read commits made through `env -S '…'`, `eval`, `xargs`, `$(which git)`, quoted names (`"g""it"`), git aliases, `python -c`, `make` and the like. After each Bash command it looks at HEAD's newest reflog entry (one local git call); a commit made during the command that the check did not see is logged as `committed` with `unseen: true`, so observe mode shows how often this happens. It needs `duration_ms` in the hook input to tell "during the command"; without it nothing is logged. Each commit is logged once per session.
- commit-gate's evidence means a verifier was invoked, not that it finished or passed. In a long autonomous turn, a verifier invoked early stays fresh until that turn ends.
- commit-gate does not see commits made through a connector (`push_files`, `create_or_update_file`) or by `git merge`, `rebase`, `cherry-pick` and `revert`.
- pr-checks looks at the working tree, not at what was pushed: the fingerprint includes uncommitted and unpushed changes, while the PR proposes the pushed head. The log's `dirty` field marks a creation with uncommitted changes; a commit that was never pushed is not detected.
- pr-checks records that the command exited 0, nothing more. A `prChecks` command that skips its tests still records a pass, and `Local-Checks: none — <reason>` is always accepted. Forging a pass locally (editing `workflow-pr-checks.json` in the git directory, or the environment) is outside what it defends against, as for commit-gate.
- pr-checks does not see a PR created by a command the parser does not read as `gh pr create` (`eval`, `xargs`, aliases, a script, `gh api`, `hub`, the web page), and it does not look again when commits are pushed to an open PR.
- pr-checks reads the tree before the Bash command runs. A git or gh command earlier in the same call that may move the branch, the tree or gh's default repo (`git switch b && gh pr create`, `git commit … && gh pr create`, `gh pr checkout 5 && gh pr create`, `gh repo set-default … && gh pr create`) makes it `unresolved` (`git push`, `fetch`, `add`, `status`, `gh pr view` and other read-only ones do not); any other command that edits files in the same call (`sed -i … && gh pr create`, `rm x && gh pr create`) is not detected. When `gh repo set-default` names a repo other than `origin`, a creation without `-R` is `unresolved`.
- pr-checks cannot tell a deleted PR body file from any other deleted untracked file: a body file that was there when the checks ran and is deleted afterwards (switching to `--body`) counts as a change. When more than 10 untracked files were there at the run, an edited body file among them counts as a change too, and so does a body file that is both a symlink and its target inside the repo when it was there at the run. Run the checks again, or keep the body outside the repo.
- pr-checks never records a pass when the command changes the tree on every run (a build output or a report that is not in `.gitignore`); ignore the output, or the gate stays at `would_block`. In `enforce` the third creation in a session is then let through as `released`.
- pr-checks needs the local `origin/HEAD` to read the repo file. The session-start lookup that fills in a missing `origin/HEAD` belongs to commit-gate and runs only under its conditions; when only `pr_checks_gate` is on and `origin/HEAD` is missing, the PR is not gated and Claude is told to run `git remote set-head origin --auto`.
- pr-checks keeps a pass across a clean rebase or a merge of the default branch: the fingerprint is the branch's change against the merge-base, so the same change on a newer base still counts, although the checks ran on the older base. CI on the PR is what covers that.
- `checks.py run` executes the command the repository's default branch declares, with your shell's permissions. In a clone you do not trust, the repo file itself can turn `enforce` on, and the denial then asks Claude to run that command; the permission prompt shows `checks.py run`, not the command behind it. The denial text shows the command, or only its length when it is over 400 characters, and tells Claude to show the user the command first in a clone that is not trusted. Read `prChecks` in `.claude/verification.json` on the default branch before letting it run, as you would a test script.
- A project `.claude/settings.json` can disable a plugin (`enabledPlugins`) and set environment variables for the session (`env`), so a PR that changes that file needs a human look at the diff; only managed settings can prevent it.

## Requirements

macOS or Linux, `python3` (3.9 or later; the stock macOS `/usr/bin/python3` is 3.9), `git`, `gh`, `jq`

## Tests

```bash
bash plugins/workflow/tests/run-all.sh
claude plugin test plugins/workflow   # rate-limits mod
```
