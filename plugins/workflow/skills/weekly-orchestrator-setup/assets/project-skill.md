---
name: __SKILL_NAME__
description: Orchestrator for __REPO__ that runs one cycle (plan, batch and delegate, verify, close out) on top of weekly-orchestrator-base. Does not implement. [TODO: one line on what this repo's cycle is for, then trigger phrases in the user's language, e.g. "plan this week", "close the week", "resume the plan"]
---

# __SKILL_NAME__ — the cycle of __REPO__

**Read and follow `weekly-orchestrator-base` first.** This skill adds only what is specific to this repository.
The role, the orchestrator session, the plan section, planning, batching, delegation, receiving results, closing out,
resuming after `/clear` and the don'ts belong to the base. If something here seems to contradict a base practice,
do not pick one silently; ask the user.

## This repository's cycle

- **Settings**: `.claude/weekly-orchestrator.json` holds the title, the week, the timezone, the boundary and the
  goal marker (keys in the base skill's `references/config.md`). Change them there, not in this file
- **Gathering and opening cycles**: the base skill's scripts (`survey.py`, `cycle.py`), run as the base skill says.
  `.github/workflows/weekly-cycle-issue.yml` creates the cycle issue as a safety net when none has its title
- **Boundary**: [TODO: when a cycle is closed (a weekday, or a submission) and who decides the time written in
  `## Result`]
- **Minimum bar sources** beyond the base ones: [TODO: or "none"]

## Shared resources

| Resource | What collides | Rule |
|---|---|---|
| [TODO] | | |

## Lines added to delegation prompts

- Read first: [TODO: e.g. AGENTS.md and the CLAUDE.md of the area the batch touches]
- Rules: [TODO: the shared-resource rules above, repo test rules]

## Extra don'ts

- [TODO: or remove this section]
