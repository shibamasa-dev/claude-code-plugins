# claude-code-plugins

English | [日本語](README.ja.md)

[![ci](https://github.com/shibamasa-dev/claude-code-plugins/actions/workflows/ci.yml/badge.svg)](https://github.com/shibamasa-dev/claude-code-plugins/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A Claude Code plugin marketplace: guard hooks and workflow skills from daily development, generalized for anyone to use.

> [!IMPORTANT]
> Plugins run hooks and scripts on your machine. Read a plugin's README (and its `hooks/`) before installing it.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install guards@shibamasa-plugins
/plugin install workflow@shibamasa-plugins
/plugin install testing@shibamasa-plugins
/plugin install repo-setup@shibamasa-plugins
/plugin install creative@shibamasa-plugins
/plugin install lint@shibamasa-plugins
/plugin install inventory@shibamasa-plugins
/plugin install instructions@shibamasa-plugins
/plugin install research@shibamasa-plugins
```

Every plugin is independent. Install only the ones you need.

## Plugins

| Plugin | What it does |
|---|---|
| [guards](plugins/guards/README.md) | Hooks that stop Claude before it does something irreversible: recursive deletes of home or system directories, deleting unmerged worktrees, pushing from a branch behind the default branch. Optional repo-layout rules. Fast-forwards the local base branch after a merge. Also blocks `gh issue view --comments` without `--json` (gh-comments-guard) and `pip freeze` (pip-freeze-guard), and, once you set `publish_patterns`, issue / PR text in `gh` commands and GitHub connector tools that matches your private-value patterns before it goes to a public repo (publish-guard; the guards README lists what it does not see) |
| [workflow](plugins/workflow/README.md) | Skills and hooks for the path from request to merge (including routing and waiting for PR reviews), issue hygiene, session handoff and runbook recording, plus a mod that writes usage limits to a file |
| [testing](plugins/testing/README.md) | Designing and running tests: Gherkin test cases, linting the test artifacts, and a gate that requires a full test run before releases |
| [repo-setup](plugins/repo-setup/README.md) | Bootstrapping a repo: a health check of the basics, a setup scaffold for cloud environments and a builder for a project's own real-app verification skill (`verification-skill-builder`) |
| [creative](plugins/creative/README.md) | Skills for image-generation prompts, diagram box semantics and code-driven motion videos |
| [lint](plugins/lint/README.md) | Tools for making skills: `skill-planner` plans a skill before it is built, and `skill-lint` checks whether it leaks details about its author, company or machine before you publish it. Also a hook that lints `DESIGN.md` after it is edited |
| [inventory](plugins/inventory/README.md) | An inventory database of the things you own. Claude registers items from photos, keeps what it couldn't read as `needs_review`, and searches with NFKC-normalized text. SQLite by default, or Postgres / Supabase directly or through a claude.ai connector |
| [instructions](plugins/instructions/README.md) | A mod that loads bundled instruction files the way Claude Code loads your `~/.claude/CLAUDE.md`, so the same working rules apply on every machine. Currently one file on reply language and linking files. No effect where managed settings or a Team / Enterprise plan seat Claude Code's built-in guard |
| [research](plugins/research/README.md) | Skills that read X and the web. Currently `research-x`, which asks xAI's X search about the X accounts you choose, keeps clear update announcements, summarizes them in your language and tone, and posts one Slack message each. The channel history is its only state |

Each plugin's README lists its skills, hooks and settings.

### Renamed plugins (2026-10)

`review` was merged into `workflow`, `devtools` became `repo-setup`, and `docs` became `creative`. If you installed the old names, reinstall:

```text
/plugin uninstall review@shibamasa-plugins
/plugin uninstall devtools@shibamasa-plugins
/plugin uninstall docs@shibamasa-plugins
/plugin marketplace update shibamasa-plugins
/plugin install workflow@shibamasa-plugins
/plugin install repo-setup@shibamasa-plugins
/plugin install creative@shibamasa-plugins
```

Move your `review` settings (`review_heavy`, `review_light`, `review_auto`, `rereview_threshold`) to the same keys in `workflow`.

## Language

English is the base language, and the plugins are being translated from Japanese. Until a plugin's CHANGELOG has an entry saying its messages and skill bodies are now in English, they are still in Japanese. Claude replies in the language you write in either way, and skill descriptions also list Japanese trigger phrases. Japanese READMEs are in `README.ja.md` next to each `README.md`.

## Requirements

- macOS or Linux, `python3`, `git`, `gh`
- `motion-video` also needs Node.js, Chrome and ffmpeg
- `inventory` also needs `uv` (to start its MCP server)
- `research` also needs an xAI API key and a Slack bot token

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the pre-commit hook, version bumps and releases. Report vulnerabilities through [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
