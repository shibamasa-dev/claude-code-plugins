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
| `python-venv` | Decides where a venv goes (the repo's `.venv`, or a shared venv per purpose when another repo or a worktree uses it), adds packages to a shared venv without breaking it, and cleans up dead venvs: a read-only inventory, `uv pip freeze`, then delete |

The test-design check in `codebase-doctor` (Check 6b) reads where test artifacts belong from the `testcase-generator` skill in [testing](../testing/README.md). Without the testing plugin, that check is SKIPPED (excluded from the score).

## Configuration

`userConfig` keys, set when you enable the plugin or later with `/plugin`:

| Key | Default | Meaning |
|---|---|---|
| `shared_venv_dir` | `~/.venvs` | Folder for venvs that more than one repo or worktree uses, one per purpose. python-venv puts shared venvs here and its inventory scans it. Empty means `~/.venvs` |

### Where files go

| What | Where |
|---|---|
| codebase-doctor reports | `.context/repo-setup/doctor/` in the repo; the skill adds `.context/` to `.git/info/exclude` first, so they stay out of git |
| What the skills set up for you to commit | in the repo: the Decided setup section of `CLAUDE.md`, `.claude/skills/verify-<app>/`, `scripts/remote-setup/` |
| The log of the generated setup script | `~/.cache/remote-setup/<repo>.log` on the machine that runs it |

python-venv writes nothing itself: its inventory script only reads. The frozen `requirements-frozen-<venv name>-<date>.txt` it asks for goes next to the venv being deleted.

It keeps nothing in its plugin data directory, so uninstalling removes none of these files.

## Requirements

macOS or Linux, `python3`, `git`, `gh`; `uv` for python-venv's install and freeze steps (the inventory needs only `python3`)

## Tests

```bash
bash plugins/repo-setup/tests/run-all.sh
```
