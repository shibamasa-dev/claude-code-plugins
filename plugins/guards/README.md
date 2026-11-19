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
| bash-guard (publish-guard) | Before Bash, and before the GitHub connector's tools that write issue / PR text | Off until `publish_patterns` is set. Checks the text about to be published (title, body, body files, heredocs) against your private-value patterns. Denies a match headed for a public repo, naming the pattern number and the place but never the matched text. A private or internal repo passes silently; when the repo or its visibility can't be determined, the call passes with a note |
| repo-structure-guard | Before Write | Active only when a rules file exists. Blocks writes that break the repo layout rules (for example, a new `.md` directly under `docs/` or a script directly under `scripts/`) |
| git-freshness | After Bash, and after a merge through the GitHub connector | After a merge, fast-forwards (`--ff-only`) the PR's base branch if you have it checked out (the default branch if the base is unknown). If it can't, it only tells you; it never blocks. For connector merges, only when the local clone is the same repo |

## Configuration

Change settings with `/plugin configure guards@shibamasa-plugins` (or `/config`).

| Key | Default | Meaning |
|---|---|---|
| `worktree_dirs` | empty | Folders where you keep worktrees (comma-separated, e.g. `~/.worktrees`). Recursive deletes inside them are allowed, and paths whose merge state can't be determined (missing, or hidden behind a variable) are blocked. Even when empty, deleting an unmerged worktree is blocked anywhere |
| `publish_patterns` | empty | Turns publish-guard on. A JSON array of regexes on one line, for example `["acme-internal", "(?i)acme-[a-z]+-private"]`. Each is matched line by line against issue / PR text before it is published; write `(?i)` into a pattern to ignore case. Stored as a sensitive value (in your system's credential store, not `settings.json`). It does not appear in `/config`: set it with `/plugin configure guards@shibamasa-plugins`, or at install time with `--config 'publish_patterns=["acme-internal"]'`. A value that is not a JSON array disables the check with a note; an entry that is not a valid regex is skipped and named by its number |

You can also pass values at install time: `claude plugin install guards@shibamasa-plugins --config worktree_dirs=~/.worktrees`. Hooks receive them as environment variables `CLAUDE_PLUGIN_OPTION_<KEY>` (e.g. `CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS`).

### What publish-guard reads

- Commands: `gh issue create|edit|comment`, `gh pr create|edit|comment|review`, `gh api` with a writing method (`-X POST|PATCH|PUT`, or implied by `-f` / `-F` / `--input`) on `repos/<owner>/<repo>/issues…` and `…/pulls…` endpoints, and `gh api graphql` (every field value)
- Text: `--title` / `-t`, `--body` / `-b`, the file of `--body-file` / `-F`, the `title` / `body` fields of `gh api` (including `-F body=@file` and `--input <file>`), every heredoc body in the same command, and files read by `$(cat <file>)`. File paths themselves are not checked
- Connector tools (matched by the end of the tool name, whatever the server is called): `issue_write`, `add_issue_comment`, `update_issue_comment`, `create_pull_request`, `update_pull_request`, `pull_request_review_write`, `add_comment_to_pending_review`, `add_reply_to_pull_request_comment`; their `title` and `body`
- Target repo, only looked up after a match: `-R` / `--repo`, the `repos/<owner>/<repo>/` path of `gh api`, `GH_REPO`, then the command directory's `gh-resolved` remote, or its only GitHub remote. Visibility is asked with `gh api repos/<owner>/<repo>` (5 s) and cached in the plugin's data directory: `public` for 7 days, anything else for an hour. A repo made public after it was cached as private is therefore unprotected for up to an hour
- A body file that can't be read yet (written later in the same command) is not checked and gets a note; a heredoc that writes it in the same command is checked

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

publish-guard catches a private value typed into the text of a command, not one that only appears when the command runs. It does not see:

- Text produced at run time: a variable set in an earlier call, `$(python …)`, `jq`, `printf` escapes, base64
- A body piped in from another program (`… | gh issue create --body-file -`); the call passes with a note that the text was not checked
- `curl` to the API, and other commands that publish (`gh release`, `gh gist`, `gh repo edit --description`, wikis, discussions, commit messages), `gh pr create --fill` (commit text) and `--web`
- Connectors whose tool names differ from the list above
- Look-alike characters (full-width letters, homoglyphs), and a value in a different case when the pattern has no `(?i)`
- `gh` flags written between `gh` and the subcommand (`gh -R owner/repo issue create`), and short flags bundled with others
- Here-strings (`<<<`) and a body redirected from a file (`--body-file - < file`)
- Where a `gh api graphql` call writes (it names its target by node id), and which repo `gh` picks in a directory with several GitHub remotes and none marked as the default: a match there passes with a note

Anything it cannot determine (the repo, its visibility, a file) is allowed with a note, not blocked. A CI scan of the published text is the backstop.

## Requirements

macOS or Linux, `python3`, `git`, `gh`

## Tests

```bash
bash plugins/guards/tests/run-all.sh
```
