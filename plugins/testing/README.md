# testing

English | [日本語](README.ja.md)

Skills and hooks for designing and running tests.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install testing@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `testcase-generator` | Writing Gherkin test cases from specs, code or PRs |

## Hooks

| Hook | When | What it does |
|---|---|---|
| testcase-lint | After Edit or Write | Checks that test-case artifacts follow the style guide |
| full-test-gate | Session start, before Bash | Reports how much has changed since the last full test run, and blocks release-like commands while unverified changes exist |

- **full-test-gate** runs only in projects whose default branch has `.claude/full-test.json`. The file is read from `origin/<default>`, not the working tree, so a branch cannot change the command or the gate it is judged by: a new or changed config takes effect once it is merged to the default branch and your local `origin/<default>` is fetched (a repo without an `origin` remote reads the working tree). The format is described at the top of [`hooks/full-test-gate.py`](hooks/full-test-gate.py). `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" run` runs the full test suite and records it if it passes; `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" run --working-tree` runs the working tree's config to try it before merging and never records; `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" status` shows the changes since the last run. The hook messages print the command with the full path

## Limitations

The checks that read their config from the default branch (full-test-gate) defend against what a branch's content can change (committed files, pushed branches). They trust the local git configuration and environment, and origin's default branch is the authority: in a fork workflow that is the fork, not `upstream`. When origin's default branch cannot be determined (no usable local `origin/HEAD` and origin unreachable), the check does not run, says so, and asks origin again no sooner than an hour later. A project `.claude/settings.json` can disable a plugin (`enabledPlugins`) and set environment variables for the session (`env`), so a PR that changes that file needs a human look at the diff; only managed settings can prevent it.

## Requirements

macOS or Linux, `python3`, `git`
