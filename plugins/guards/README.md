# guards

English | [日本語](README.ja.md)

Hooks that stop Claude Code before it does something you can't undo.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install guards@shibamasa-plugins
```

## Hooks

| Hook | When | What it does |
|---|---|---|
| bash-guard | Before Bash | Blocks recursive deletes of home or system directories, deleting an unmerged worktree (wherever it lives, including `.claude/worktrees` inside a repo), and pushing from a branch that is behind the default branch (asked from origin; falls back to the local `origin/HEAD`, then `main` / `master`). Deletes outside the safe area are allowed through macOS `trash`. Deleting a merged, clean worktree is allowed. Also blocks (gh-comments-guard) `gh issue view --comments` without `--json` (it prints nothing on an issue with no comments; only a command that starts with `gh` is checked, so `env gh ...` and other wrappers pass) and (pip-freeze-guard) `pip freeze` (empty in uv-made venvs; use `uv pip freeze`, adding `--python <path>` to target an environment other than the active one, or prefix `PIP_FREEZE_OK=1`) |
| repo-structure-guard | Before Write | Active only when a rules file exists. Blocks writes that break the repo layout rules (for example, a new `.md` directly under `docs/` or a script directly under `scripts/`) |
| git-freshness | After Bash, and after a merge through the GitHub connector | After a merge, fast-forwards (`--ff-only`) the PR's base branch if you have it checked out (the default branch if the base is unknown). If it can't, it only tells you; it never blocks. For connector merges, only when the local clone is the same repo |

## Configuration

Change settings with `/plugin configure guards@shibamasa-plugins` (or `/config`).

| Key | Default | Meaning |
|---|---|---|
| `worktree_dirs` | empty | Folders where you keep worktrees (comma-separated, e.g. `~/.worktrees`). Recursive deletes inside them are allowed, and paths whose merge state can't be determined (missing, or hidden behind a variable) are blocked. Even when empty, deleting an unmerged worktree is blocked anywhere |

You can also pass values at install time: `claude plugin install guards@shibamasa-plugins --config worktree_dirs=~/.worktrees`. Hooks receive them as environment variables `CLAUDE_PLUGIN_OPTION_<KEY>` (e.g. `CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS`).

### Repo layout rules (repo-structure-guard)

The hook runs only when a rules file exists. It uses the first one found, in this order, and does nothing if none exists:

1. The environment variable `REPO_STRUCTURE_SPEC`. If set, only this is used; a path that doesn't exist disables the hook
2. `.claude/rules/repo-structure.md` on the default branch (`origin/<default>`) of the repo being written to. Commit it to share it with your team and cloud sessions; Claude also reads it as a rule. It is read from the default branch, not the working tree, so a new or changed rule takes effect once it is merged and your local `origin/<default>` is fetched; until then the next source applies. A repo without an `origin` remote reads the working tree
3. `~/.claude/rules/repo-structure.md` (all your repos)

Copy [`examples/repo-structure.md`](examples/repo-structure.md) to one of these and edit it. Only `<!-- guard:… -->` blocks are used for decisions.

## Merges

guards doesn't gate merges. Merge conditions (reviews done, a `## Result` section on the issue the PR closes) belong to the workflow plugin's `dev-flow` skill and `dev-flow-gate` hook. With guards alone, merges aren't stopped.

## Limitations

guards is a safety net against Claude's mistakes, not a sandbox against malicious commands. Commands built in ways the hooks can't parse may get through.

The checks that read their config from the default branch (repo-structure-guard) defend against what a branch's content can change (committed files, pushed branches). They trust the local git configuration and environment, and origin's default branch is the authority: in a fork workflow that is the fork, not `upstream`. When origin's default branch cannot be determined (no usable local `origin/HEAD` and origin unreachable), the check does not run, says so, and asks origin again no sooner than an hour later. A project `.claude/settings.json` can disable a plugin (`enabledPlugins`) and set environment variables for the session (`env`), so a PR that changes that file needs a human look at the diff; only managed settings can prevent it.

## Requirements

macOS or Linux, `python3`, `git`, `gh`

## Tests

```bash
bash plugins/guards/tests/run-all.sh
```
