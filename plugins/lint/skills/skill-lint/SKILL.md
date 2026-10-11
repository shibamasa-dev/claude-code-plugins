---
name: skill-lint
description: Checks whether a skill (SKILL.md plus attached files such as scripts/ and references/) contains information specific to the person, company or machine that made it, and reports whether it is safe to distribute to anyone. Catches names of people, companies and clients, home absolute paths and defaults pointing at personal directories, internal hosts, private issue numbers, decision history, dependencies on private bots or private repos, and runtime data inside the skill. Use only when the user types /lint:skill-lint, or when an injected instruction after using skill-creator asks for it. Do not start it on your own judgment otherwise.
argument-hint: <skill directory>
---

# skill-lint — check whether a skill is safe to distribute

The question is: "If someone at another company installs this skill on another machine, does it still work? What does it reveal to them?" It checks in two layers.

1. **lint.py (deterministic)**: catches things mechanically with generic regular expressions only (email addresses, home paths, tailnet hosts, issue numbers, decision history, runtime data, secrets). A cheap preprocessing pass
2. **reviewer (agent)**: gathers proper-noun hints from the runtime environment itself, uses the lint results as hints too, and judges names of people, companies and clients, dependencies on private bots or private repos, and steps that assume a specific environment. The reviewer is the main judge of proper nouns and meaning

## Invariants

1. **Never fix anything on your own.** Report, then ask the user whether to fix.
2. **Never build a list of proper nouns anywhere.** Keep no file that collects names (a denylist). The reviewer gathers and judges them on the spot.
3. **Report only reviewer findings that passed validate_findings.py.** Drop any finding whose quote is not verbatim in that line.

## Steps

The target is `$ARGUMENTS` (a skill directory). If missing, ask the user. Keep working files in the session's temporary directory (or `mktemp -d` if there is none). `<tmp>` below means that location.

### 1. Run lint.py

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/skill-lint/scripts/lint.py" "$ARGUMENTS" --json > <tmp>/lint.json
```

| Category | Severity | What it catches |
|---|---|---|
| identity | error | Email addresses (proper nouns are not checked; the reviewer judges them) |
| path | error | Absolute paths under a home directory (macOS, Linux, Windows) |
| path | warn | Home-relative paths outside the standard ones (`~/.claude/`, `~/.config/`, `~/.local/`, `~/.cache/`). Tool locations right under home (hidden directories, the OS's standard folders) also match, so the reviewer decides whether it is a personal directory layout |
| network | error | tailnet host names |
| secret | error | Secrets found by gitleaks, or a gitleaks failure (including an unreadable report) |
| structure | error | Runtime data inside the skill: `logs/`, `.trash/`, `*.db`, `*.sqlite`, `*.jsonl`, `*.log`, etc. |
| tracker | warn | `owner/repo#N`, `repo#N`, bare `#N` |
| provenance | warn | A date and a decision word on the same line: Japanese (確定・承認・指示・判断・確認 — confirmed, approved, instructed, decided, checked) or English (approved, decided, confirmed, instructed, agreed, signed off; whole words, any case) |

- Frontmatter `last_reviewed` / `review_after` are not checked. Lines containing `skill-lint: ignore` are not checked either.
- Only paths listed in the target skill's `.skill-lint-ignore` are excluded (by default every file is checked; fixtures taken from real data leak the most, so exclude nothing except test data that leaks on purpose). The number of excluded files is reported.
- In plugin manifests (`.claude-plugin/plugin.json`, `marketplace.json`), publisher lines (`name`, `author`, `owner`, `homepage`, `repository`) are public by design, so only email addresses are skipped there (paths and hosts are still checked).
- Unreadable files are reported as `unreadable` (error). They are never skipped silently.
- If `gitleaks` is on PATH, secret checks are delegated to it. Otherwise `gitleaks.status` is `skipped`.
- Exit code is 1 if there are errors, 0 if there are only warnings.

### 2. Start the reviewer

Start one `Agent(subagent_type: general-purpose)`. Build its prompt by concatenating, in this order:

1. The full text of `${CLAUDE_PLUGIN_ROOT}/skills/skill-lint/references/reviewer-prompt.md`
2. The absolute path of the target directory and the instruction "Read every file with Read (except lint.py's `excluded_files`)"
3. Hints: the `findings` from `<tmp>/lint.json`, keeping only `file`, `line`, `category` and `match`
4. "Output only the JSON array"

The procedure for gathering proper-noun hints from the runtime environment (`whoami`, `git config`, `gh api user`, `hostname`) is in reviewer-prompt.md; the reviewer does it itself.

Save the reviewer's final output as is to `<tmp>/review.txt`.

### 3. Validate with validate_findings.py

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/skill-lint/scripts/validate_findings.py" "$ARGUMENTS" <tmp>/review.txt > <tmp>/review.json
```

Use only `valid` in the report. For `invalid`, report just the count and reasons. If no JSON array can be extracted (exit 2), restart the reviewer once.

### 4. Write the combined report

Group by category, and give each finding its location (`file:line`), what is leaking, and how to fix it. If lint and the reviewer both caught the same word on the same line, merge them into one. Start with these lines, one each:

- Verdict: "safe to distribute" if there are 0 errors and 0 reviewer findings with `high` confidence; otherwise "fix before distributing"
- Counts: lint errors / warnings, reviewer valid / invalid
- gitleaks status and the number of excluded files

Write the report in the user's language.

### 5. Ask whether to fix

Ask "Fix them? (all / pick / none)" and stop. When fixing, first show the replacement for each finding (a role name, an environment variable or a placeholder), then edit, and when done start again from step 1 and confirm zero findings.

## Attached files

| File | Role |
|---|---|
| `scripts/lint.py` | Deterministic checks. `--json` for machines, plain for humans |
| `scripts/validate_findings.py` | Extracts the JSON array from the reviewer output and matches each quote against its line |
| `references/reviewer-prompt.md` | Instructions for the reviewer (viewpoint, what to catch, what is not a leak, output format) |
| `scripts/run_evals.py` | Eval group A (runs lint.py on the fixture and grades it) |
| `scripts/run_reviewer_eval.py` | Eval group B (runs the reviewer with `claude -p` and counts recall and false positives. `--runs N`) |
