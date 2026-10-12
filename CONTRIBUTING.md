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
```

## Language and READMEs

- Write everything in English: skills, hook messages, comments, tests, manifests and CHANGELOG entries
- Skill `description` fields also list the Japanese trigger phrases, so Japanese prompts still trigger the skill. Write a description on one line, at 1024 characters or fewer: claude.ai cuts a longer one when it syncs the plugin, and `check-repo.py` fails it (it measures one-line values only)
- CI fails a PR whose added lines contain Japanese outside quotes. Quote Japanese data (`code`, 「quotes」, string literals) or add `ja-ok` to the line; `README.ja.md`, `tests/`, `evals/` and `fixtures/` are not checked. Check locally with `python3 .github/scripts/check-repo.py --base origin/main`
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
