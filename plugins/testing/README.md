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

- **full-test-gate** runs only in projects that have `.claude/full-test.json`. The format is described at the top of [`hooks/full-test-gate.py`](hooks/full-test-gate.py). `full-test-gate run` runs the full test suite and records it if it passes; `full-test-gate status` shows the changes since the last run

## Requirements

macOS or Linux, `python3`, `git`
