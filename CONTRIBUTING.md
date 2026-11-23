# Contributing

Issues and pull requests are welcome in English or Japanese.

## Pre-commit hook

The repo ships a pre-commit hook that stops personal details (absolute home paths, email addresses) from being committed and checks the commit author's email. Install it once per clone (and again when the hook changes), after reading it:

```bash
bash .githooks/install.sh
```

It copies the hook and the check script from `origin/main` into `.git/hooks/` (it never runs files from the working tree, so checking out an external PR branch doesn't run that branch's code). `install.sh` itself runs from the working tree, so read it with `main` checked out before running it. If you already use hooks from somewhere else (such as a global `core.hooksPath`), it doesn't write there; it calls them after its own check.

To block additional proper names, put one regex per line in `~/.config/claude-code-plugins/blocked-patterns` (never in the repo). CI (`.github/workflows/`) runs the same check.

## Before opening a PR

Run the same checks as CI locally:

```bash
claude plugin validate --strict .
for p in plugins/*/; do claude plugin validate --strict "$p"; done
python3 .github/scripts/check-repo.py
for t in plugins/*/tests/run-all.sh; do bash "$t"; done   # tests assume macOS
claude plugin test plugins/instructions                    # mod tests (*.test.ts)
claude plugin test plugins/workflow
```

CI also runs these. Run them when you touch the parts they cover:

```bash
# The plugin suites under Python 3.9 (the python3 of a stock macOS); needs uv
d=$(dirname "$(uv python find 3.9)")
PATH="$d:$PATH" python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 9) else "python3 is %d.%d" % sys.version_info[:2])' &&
  for t in plugins/*/tests/run-all.sh; do PATH="$d:$PATH" bash "$t"; done

# The inventory tests against Postgres (a throwaway postgres:16 container); needs docker, psql and uv
bash plugins/inventory/tests/run-postgres.sh

# The agent-bridge schema tests against Postgres (a throwaway postgres:16 container); needs docker and psql
bash plugins/agent-bridge/tests/run-postgres.sh

# The creative image history tests against Postgres (a throwaway postgres:16 container); needs docker, psql and uv
bash plugins/creative/tests/run-postgres.sh
```

CI installs the Claude Code CLI at the version in `.github/claude-code-version` (`ci.yml` and `release.yml` both read it). To raise it, change that file in a PR; CI on the PR runs the validate and mod-test steps with the new version.

## Issue and PR text

`text-scan.yml` checks the text of issues and PRs (titles, bodies, comments, reviews) with the same patterns as the file check, on every text event and in a daily sweep. A match adds the `private-value` label and fails the run; the summary names the item and field only. To clear it: edit the text, delete the old revision from the comment's edit history, then remove the label by hand (the workflow never removes it). Run it locally, read-only, with `GITHUB_REPOSITORY=<owner>/<repo> GITHUB_TOKEN=$(gh auth token) python3 .github/scripts/leak/scan-text.py --issue <n> --dry-run`, and its tests with `python3 -m unittest discover -s .github/scripts/leak/tests`.

Limits to know about:

- The label and the run result are public, so an outside author can post a candidate name and see whether it matched, one guess per comment. The output hides which pattern matched, where and how many times, which slows probing down but does not prevent it
- The built-in patterns cover two classes only: a home directory path and an e-mail address. Account names, private repository names and similar values are caught only when the `BLOCKED_PATTERNS` secret lists them
- In issue and PR text the home-path pattern skips example paths (placeholder names such as `user` or `alice`) and paths that do not start at a boundary; the file check does not

## Language and READMEs

- Write everything in English: skills, hook messages, comments, tests, manifests and CHANGELOG entries
- Skill `description` fields also list the Japanese trigger phrases, so Japanese prompts still trigger the skill. Write a description on one line, at 1024 characters or fewer: claude.ai cuts a longer one when it syncs the plugin, and `check-repo.py` fails it (it measures one-line values only)
- CI fails a PR whose added lines contain Japanese outside quotes. Quote Japanese data (`code`, 「quotes」, string literals) or add `ja-ok` to the line; `README.ja.md`, `tests/`, `evals/`, `fixtures/` and lines inside a `<!-- lint:TAG -->` … `<!-- /lint:TAG -->` block (data a hook reads line by line, which takes neither quotes nor `ja-ok`) are not checked. Check locally with `python3 .github/scripts/check-repo.py --base origin/main`
- Every `README.md` has a Japanese `README.ja.md` next to it, linked from a language switcher on line 3. Update both in the same PR. `check-repo.py` enforces the pair

## Versions and CHANGELOG

- When you change a plugin's contents, bump `version` in its `plugin.json`. With the same version, `claude plugin update` assumes the plugin is up to date and doesn't replace it. CI (`check-version-bump.sh`) fails PRs that don't bump. Changes only to `README.md`, `README.ja.md`, `CHANGELOG.md` or `tests/` are exempt
- After bumping, add a heading for the same version to the plugin's `CHANGELOG.md` (`## [0.1.3] - 2026-10-06`, dated the day you open the PR) with the user-visible changes. CI fails without it
- Don't put `version` in the `marketplace.json` entries (`plugin.json` wins, and having both makes validate warn)

## Releases

After a merge to `main` passes CI, `release.yml` tags each plugin whose version went up as `<plugin>--v<version>` (e.g. `guards--v0.1.3`). It runs `claude plugin tag --push`, which also stops on a version mismatch between `plugin.json` and `marketplace.json`. Before tagging it runs the same proper-name check as leak-scan.

To tag a release that was missed, update `main` and confirm CI is green first:

```bash
claude plugin tag plugins/guards --dry-run   # check
claude plugin tag plugins/guards --push
```
