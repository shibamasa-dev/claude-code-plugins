
## Weekly plan

The orchestrator session `🎯 __REPO_NAME__` runs the cycle with `.claude/skills/__SKILL_NAME__/`, built on `weekly-orchestrator-base` (workflow plugin).
Its source of truth is the plan section of the cycle issue (`__TITLE_FORMAT__`); the cycle's settings are in `.claude/weekly-orchestrator.json`.
`.github/workflows/weekly-cycle-issue.yml` creates that issue as a safety net; never create a second issue with the same title.
