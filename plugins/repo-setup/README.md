# repo-setup

English | [日本語](README.ja.md)

Skills for bootstrapping a repo.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install repo-setup@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `codebase-doctor` | Checks whether a repo has the basics in place (tests, CI, lint, initial security settings, …) |
| `remote-setup` | Creates a setup scaffold for cloud environments such as claude.ai/code and Cowork |

The test-design check in `codebase-doctor` (Check 6b) reads where test artifacts belong from the `testcase-generator` skill in [testing](../testing/README.md). Without the testing plugin, that check is SKIPPED (excluded from the score).

## Requirements

macOS or Linux, `python3`, `git`, `gh`
