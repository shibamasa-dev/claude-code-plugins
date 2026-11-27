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
/plugin install diagram@shibamasa-plugins
/plugin install lint@shibamasa-plugins
/plugin install inventory@shibamasa-plugins
/plugin install instructions@shibamasa-plugins
/plugin install research@shibamasa-plugins
/plugin install hr@shibamasa-plugins
/plugin install agent-bridge@shibamasa-plugins
/plugin install print@shibamasa-plugins
```

Every plugin is independent. Install only the ones you need.

## Plugins

| Plugin | What it does |
|---|---|
| [guards](plugins/guards/README.md) | Hooks that stop Claude before it does something irreversible: recursive deletes of home or system directories, deleting unmerged worktrees, pushing from a branch behind the default branch. Optional repo-layout rules. Fast-forwards the local base branch after a merge. Also blocks `gh issue view --comments` without `--json` (gh-comments-guard) and `pip freeze` (pip-freeze-guard), and, once you set `publish_patterns`, issue / PR text in `gh` commands and GitHub connector tools that matches your private-value patterns before it goes to a public repo (publish-guard; the guards README lists what it does not see) |
| [workflow](plugins/workflow/README.md) | Skills and hooks for the path from request to merge (including routing and waiting for PR reviews), issue hygiene, session handoff and runbook recording, plus a mod that writes usage limits to a file |
| [testing](plugins/testing/README.md) | Designing and running tests: Gherkin test cases, linting the test artifacts, and a gate that requires a full test run before releases |
| [repo-setup](plugins/repo-setup/README.md) | Bootstrapping a repo: a health check of the basics, a setup scaffold for cloud environments and a builder for a project's own real-app verification skill (`verification-skill-builder`) |
| [creative](plugins/creative/README.md) | Skills for image-generation prompts (with an image history in SQLite or Postgres) and code-driven motion videos |
| [diagram](plugins/diagram/README.md) | Skills for drawing diagrams as code. `one-page-diagram` draws an overview or concept diagram as SVG, keeping the kinds of element from mixing; `typed-diagram` draws flowcharts, sequence, state, ER and C4 diagrams in Mermaid, or as polished SVG for proposals and client documents. Both can step through several points on one figure, and both render the result and look at it before delivering, and say so when they could not |
| [lint](plugins/lint/README.md) | Tools for making skills: `skill-planner` plans a skill before it is built, and `skill-lint` checks whether it leaks details about its author, company or machine before you publish it. Also a hook that lints `DESIGN.md` after it is edited |
| [inventory](plugins/inventory/README.md) | An inventory database of the things you own. Claude registers items from photos, keeps what it couldn't read as `needs_review`, and searches with NFKC-normalized text. SQLite by default, or Postgres / Supabase directly or through a claude.ai connector |
| [instructions](plugins/instructions/README.md) | A mod that loads bundled instruction files the way Claude Code loads your `~/.claude/CLAUDE.md`, so the same working rules apply on every machine. Currently one file on reply language and linking files. No effect where managed settings or a Team / Enterprise plan seat Claude Code's built-in guard |
| [research](plugins/research/README.md) | Skills that read X and the web. `research-x` asks xAI's X search about the X accounts you choose, keeps clear update announcements, summarizes them in your language and tone, and posts one Slack message each; the channel history is its only state. `read-x-article` reads one X post or X Article from its URL through the fxtwitter API, summarizes it, and saves a Markdown copy only when you ask |
| [hr](plugins/hr/README.md) | Japan-specific HR and labour admin. Currently `employee-certificate`, which fills the certificates a company issues to an employee (the employment certificate for nursery and after-school applications, proof of enrolment, separation certificates, proof of income) on the requester's Excel form, mapped by item label so a changed layout still fills, from company and employee files you keep outside the plugin |
| [agent-bridge](plugins/agent-bridge/README.md) | Two-way messaging between Claude Code and other AI agents through a message queue you host on Supabase. Every agent uses one API with its own token and is woken by a webhook or by polling; a listening Claude Code session wakes when a message arrives. A setup skill builds the bridge in your Supabase project with placeholder Vault secrets you replace |
| [print](plugins/print/README.md) | Prints local files (PDF, image, text, HTML, Markdown) through CUPS `lp`: black and white, duplex long edge, A4 and plain paper by default, with page numbers. It picks the options each printer accepts from `lpoptions -l`, reports what the printer doesn't take, and shows pages, sheets and settings before sending |

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
- `inventory` and `creative` also need `uv` (to start their MCP servers)
- `research`'s `research-x` also needs an xAI API key and a Slack bot token
- `agent-bridge` also needs a Supabase project and a Supabase connector (claude.ai connector or MCP server) for setup
- `print` also needs CUPS (`lp`), poppler, and Chrome for HTML, Markdown and text; qpdf and pandoc are optional

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the pre-commit hook, version bumps and releases. Report vulnerabilities through [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
