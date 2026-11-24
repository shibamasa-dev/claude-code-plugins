---
name: weekly-orchestrator-setup
description: One-time set-up of a repository's orchestrator (the 🎯 session that runs weekly-orchestrator-base). Asks for the repo's cycle settings, writes .claude/weekly-orchestrator.json, then places a project orchestrator skill template, the weekly cycle-issue GitHub Actions workflow and a three-line "Weekly plan" section in AGENTS.md or CLAUDE.md, and checks the title the scripts compute. Use when a repo has no orchestrator yet and the user wants one, or in Japanese 「新しいリポでオーケストレータを立ち上げて」「🎯 セッションを作って」「このリポにオーケストレータを入れて」「週次の計画 issue を自動で起票したい」「オーケストレータの初期設定」. Not for running a cycle (that is weekly-orchestrator-base and the project skill).
last_reviewed: 2026-11-24
review_after: 2027-05-24
---

# weekly-orchestrator-setup — give a repository its orchestrator

Run once per repository. Afterwards the repository has:

| File | What it is |
|---|---|
| `.claude/weekly-orchestrator.json` | The repo's cycle settings (keys in `weekly-orchestrator-base` `references/config.md`) |
| `.claude/skills/<name>/SKILL.md` | The project orchestrator skill: "read and follow weekly-orchestrator-base" plus blanks for this repo |
| `.github/workflows/weekly-cycle-issue.yml` | Creates the cycle issue as a safety net when none has its title |
| A "Weekly plan" section in `AGENTS.md` (or `CLAUDE.md`) | Three lines that point any session at the orchestrator and the cycle issue |

The title and week are computed only by the base skill's `cycle.py`; the workflow runs the same script, pinned to
the plugin release, so the orchestrator and the workflow cannot name the same cycle differently. The repo never
copies the plan-section template.

## Steps

1. **Check the repo.** It has a GitHub `origin` and `gh auth status` passes. If `.claude/weekly-orchestrator.json`
   or `.github/workflows/weekly-cycle-issue.yml` already exists, the repo is set up: stop and tell the user (to
   change settings, edit the config)
2. **Ask the user in one message**, offering the default in brackets, and only for what the user has not already said:
   - Cycle: the weekday the title carries and how the week is cut (`anchor_weekday`, `lead_days`; e.g. a Monday
     cycle where a weekend run plans the coming Monday is `monday` + `2`; a cycle titled by a Friday due date is
     `friday` + `6`) [`monday`, `0`: Monday to Sunday]
   - Title format with `{date}` or `{iso_week}` [`Orchestrator: {repo_name} {iso_week}`]
   - Timezone (IANA name) [the user's own; `UTC` if unknown]
   - Boundary: `Cutoff` (a fixed time) or `Submitted` (a submission closes the cycle) [`Cutoff`]
   - Goal marker in goal issue titles [none: top-level issues with sub-issues are goals]
   - Other repos the cycle covers (`extra_repos`, or `repos_from_additional_directories`) [none]
   - Issue Fields the workflow sets on a new cycle issue [none]. The field and option IDs come from the
     organization's own plugin, when one is installed; never guess IDs
   - When the workflow runs: local weekday and hour [the anchor weekday, 07:17]
   - The project skill's name [`<repo>-weekly`] and the notes file [`AGENTS.md`, or `CLAUDE.md` when there is no
     `AGENTS.md`]
3. **Write `.claude/weekly-orchestrator.json`** with only the keys that differ from the defaults
4. **Place the files.** From the repo's root, first with `--dry-run`, then without:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/weekly-orchestrator-setup/scripts/scaffold.py" --skill-name <name> --run-weekday <weekday> --hour <hour> --notes <AGENTS.md|CLAUDE.md> --dry-run
   ```
   It refuses to overwrite an existing skill or workflow file and leaves a notes file that already has a
   `## Weekly plan` heading alone. It prints the cron line (UTC) and this cycle's title
5. **Check the title.** Show the user what the scripts compute, from the repo's root:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/weekly-orchestrator-base/scripts/cycle.py" resolve
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/weekly-orchestrator-base/scripts/cycle.py" new
   ```
   The title must be what the user expects for this cycle. If not, fix the config and run them again
6. **Fill the project skill's `[TODO: …]` blanks with the user**: the boundary (when a cycle closes and who decides
   the time in `## Result`), extra minimum-bar sources, the shared-resource table, lines for delegation prompts,
   extra don'ts. Write the trigger phrases in the user's language. Leave out what the user does not know yet as a
   `[TODO: …]`; do not invent it
7. **Open a PR** for the new files following `dev-flow` (the workflow starts running once it is on the default
   branch; `workflow_dispatch` runs it by hand). Do not create the first cycle issue here: the orchestrator opens it
   in its first planning step (weekly-orchestrator-base step 1)
8. **Tell the user to create the orchestrator session**: a session in this repo titled `🎯 <repo name>`, pinned in
   the sidebar, which starts by reading the project skill

## Keeping it current

- The workflow pins the scripts to the workflow plugin release it was set up with (`ref: workflow--v<version>`).
  When the installed plugin is updated, update that `ref` in the same week; the base skill's survey warns when the
  two differ
- Change the cycle (weekday, title, timezone) in the config only. A new title format goes with the old one in
  `legacy_titles`
