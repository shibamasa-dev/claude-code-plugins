# The repo's orchestrator config (`.claude/weekly-orchestrator.json`)

One JSON file per repository, committed, at `.claude/weekly-orchestrator.json`. It holds what differs between repos
so the base scripts (`scripts/cycle.py`, `scripts/survey.py`, `scripts/create-cycle-issue.sh`) stay the same
everywhere. The orchestrator skill and the weekly-issue workflow read the same file, so a title or a week can only be
computed one way. Without the file every key takes its default below, which is the base skill's
"Defaults when the repository has no project skill". An unknown key is an error (a typo would otherwise be ignored).

| Key | Default | Meaning |
|---|---|---|
| `repo` | `$GITHUB_REPOSITORY`, then `git remote get-url origin` | `owner/name` where the cycle issues live |
| `title` | `Orchestrator: {repo_name} {iso_week}` | Cycle issue title. Must contain `{date}` (the anchor day, `YYYY-MM-DD`) or `{iso_week}` (`YYYY-Www` of the anchor day); may contain `{repo_name}` |
| `legacy_titles` | `[]` | Older title formats that still count as cycle issues (read, never written) |
| `anchor_weekday` | `monday` | Weekday of the day the title carries (the cycle's first day, or its due day) |
| `lead_days` | `0` | Days before the anchor day that already belong to its cycle. A day `d` belongs to the cycle whose anchor `A` has `A - lead_days <= d < A - lead_days + 7` |
| `timezone` | `UTC` | IANA name. Every date (title, week, `## Result` times, cron) is computed in it, on the runner (UTC) and on a laptop alike. A name that cannot be resolved stops the script |
| `period` | `{start} to {end}` | Fills `{period}` in the plan section heading |
| `boundary` | `Cutoff` | First line of `## Result`: `Cutoff` or `Submitted` |
| `goal_marker` | (empty) | Substring of goal issue titles. Empty: a goal is a top-level open issue that has sub-issues |
| `plan_extra` | (empty) | Repo file inserted into the plan section right after the `Plan status` line (extra headings such as milestones) |
| `footer` | (empty) | Repo file appended after the plan section (notes, a report checklist) |
| `extra_repos` | `[]` | More `owner/name` repos the survey reads (their issues are written `owner/repo#N`) |
| `repos_from_additional_directories` | `false` | Also read the GitHub repos behind `.claude/settings.json` `permissions.additionalDirectories` |
| `fields` | `{"priority": "Priority", "arch_review": "Arch Review", "start": "Start date", "target": "Target date"}` | Names of the Issue Fields the survey reads |
| `issue_fields` | `[]` | Values the workflow sets on an issue it creates, best effort: `{"fieldId": …, "singleSelectOptionId": …}` or `{"fieldId": …, "dateValue": "{next}"}` |

Placeholders in `title`, `period`, `plan_extra`, `footer` and `dateValue`: `{date}` (anchor day), `{start}`
(`{date}` minus `lead_days`), `{end}` (`{start}` + 6 days), `{next}` (`{date}` + 7 days, the next cycle's anchor),
`{iso_week}`, `{repo_name}`, `{repo}`.

## Examples

A Monday cycle, run on weekdays, where a weekend run already plans the coming Monday:

```json
{
 "title": "sample-app weekly {date}",
 "anchor_weekday": "monday",
 "lead_days": 2,
 "timezone": "Asia/Tokyo",
 "period": "{date} to {end}",
 "goal_marker": "[Goal]"
}
```

A cycle that ends with a submission due on Friday, titled with the due date:

```json
{
 "title": "sample-app report {date}",
 "anchor_weekday": "friday",
 "lead_days": 6,
 "timezone": "Asia/Tokyo",
 "period": "due {date}",
 "boundary": "Submitted",
 "footer": ".claude/skills/sample-weekly/report-checklist.md"
}
```

## Rules

- **The template is the base one.** `cycle.py` builds the plan section from this skill's `references/plan-section.md`;
  a repo adds headings through `plan_extra` and text outside the section through `footer`, and never copies the
  template (copies fall behind it: missing PRs column, missing Goal progress table)
- **Issue Field IDs stay in the repo.** `issue_fields` takes the organization's field and option IDs; fill them at
  set-up from the values the organization's own plugin provides, or leave the list empty
- **Changing the title format** renames future cycle issues only. Put the old format in `legacy_titles` so the
  survey and `new --prev` still find the previous cycle
