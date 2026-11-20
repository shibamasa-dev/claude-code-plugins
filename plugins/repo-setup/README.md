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
| `codebase-doctor` | Checks whether a repo has the basics in place (tests, CI, lint, initial security settings, …). In an empty repo it asks the purpose, proposes a stack and records it in CLAUDE.md |
| `remote-setup` | Creates a setup scaffold for cloud environments such as claude.ai/code and Cowork |
| `verification-skill-builder` | Writes a project's own `verify-<app>` skill that drives the real app in script order in an isolated run, keeps observed evidence, and maps each feature as action → command → result |

The test-design check in `codebase-doctor` (Check 6b) reads where test artifacts belong from the `testcase-generator` skill in [testing](../testing/README.md). Without the testing plugin, that check is SKIPPED (excluded from the score).

## Configuration

### Where files go

| What | Where |
|---|---|
| codebase-doctor reports | `.context/repo-setup/doctor/` in the repo; the skill adds `.context/` to `.git/info/exclude` first, so they stay out of git |
| What the skills set up for you to commit | in the repo: the Decided setup section of `CLAUDE.md`, `.claude/skills/verify-<app>/`, `scripts/remote-setup/` |
| The log of the generated setup script | `~/.cache/remote-setup/<repo>.log` on the machine that runs it |

It keeps nothing in its plugin data directory, so uninstalling removes none of these files.

## Requirements

macOS or Linux, `python3`, `git`, `gh`
