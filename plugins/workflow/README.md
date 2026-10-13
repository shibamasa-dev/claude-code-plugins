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
| `pr-review-triage` | Right after opening a PR or pushing to one, routes the review by the size of the diff. Light PRs (docs only, or up to 200 lines) follow `review_light`: with the default `claude`, Claude reviews and writes the result in the PR body, then waits only for CI; list tool ids (alone or next to `claude`) to also wait for those tools. Heavy PRs are sent to review tools (CodeRabbit, Codex, …) through a connector — or, in repos where the tool's auto review is on, not requested, and only light PRs are excluded from auto review with the `review:light` label — then the results are awaited, assessed and addressed. Also decides whether to request a re-review |
| `issue-ops` | Conventions from filing an issue to closing it (how to write the body, writing results back before closing) |
| `session-wrap` | Checks for leftovers before closing a session and leaves a handoff for the next one |
| `context-diet` | Measures and trims the context loaded at every session start |
| `weekly-orchestrator-base` | A base for an orchestrator that runs a weekly plan → delegate → check → close loop |

## Hooks

| Hook | When | What it does |
|---|---|---|
| handoff | Session start | Injects the "next entry point" left by the previous session. Write an entry with `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" write --entry <owner>/<repo>#<n> --state "..." --next "..."` and clear one with `... consume --entry <entry>`; the injected text prints the exact command |
| issue-writeback | Session start, prompt submit, stop, session end, after issue operations | Reminds you if decisions were not written back to an issue you read |
| runbook | After browser or computer-use actions, on stop, at session start | Records browser and screen-operation steps, and stops if you forgot to write the runbook |
| knowledge-freshness | Session start | Reports knowledge files past their review date in one line |
| artifact-ledger | After Artifact | Records published Artifacts in the project's `.artifacts/` |
| dev-flow-gate | Before creating a PR | Blocks if the body lacks `Closes #N` / `Refs #N` (`Refs: none (verbal request)` for requests without an issue) or the `Arch-Review:` field |
| | After creating a PR | Tells Claude the next stage (wait for reviews and CI) |
| | Before ending a turn | Blocks once per PR if waiting (a PR event subscription or a Monitor) has not started for a PR created in this session |
| | Before a merge | Blocks if there is no record that the `## Result` section (the older `## 結果` also counts) of the issue the PR closes was written or read and confirmed |

dev-flow-gate watches both the GitHub connector (`create_pull_request`, `merge_pull_request`, `enable_pr_auto_merge`, `issue_read`, `issue_write`) and `gh`. It never queries GitHub itself; it decides only from tool calls made in the session (merging a PR created in another session isn't blocked, it just asks Claude to check). State lives in `${CLAUDE_PLUGIN_DATA}/dev-flow-gate/<session_id>.json`, and files older than 30 days are removed at session start.

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

Available tool ids are the file names in `skills/pr-review-triage/references/tools/` (`codex`, `coderabbit`, `copilot`, `gemini`, `cursor-bugbot`).

To override per repo, add lines to the repo's CLAUDE.md (or AGENTS.md). Lines take precedence over userConfig. `review-notes:` is free text describing what reviewers should focus on; it goes into the request and into Claude's review (it isn't used for routing):

```
review-heavy: coderabbit, codex
review-light: claude
review-auto: on
review-notes: please look closely at permission changes
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

## Commands

- `/workflow:dev-process:review-and-fix` — runs AI review → assessment → fix plan → implementation in one go

## Organization values

Organization values (GitHub org, default repo, Issue Fields, project board) aren't stored in the skills. The skills read an injected text block headed "Organization settings" (or 「組織設定」) from the session context if present, otherwise the project's CLAUDE.md. Internal values are meant to be injected by a separate plugin through a SessionStart hook.

## Storage

| Environment variable | Default | Contents |
|---|---|---|
| `HANDOFF_STATE_DIR` | `~/.claude/state/handoff` | handoff entry points |
| `RUNBOOK_ROOT` | `~/.claude/runbooks` | runbook raw logs and written runbooks |

## Requirements

macOS or Linux, `python3`, `git`, `gh`, `jq`

## Tests

```bash
bash plugins/workflow/tests/run-all.sh
claude plugin test plugins/workflow   # rate-limits mod
```
