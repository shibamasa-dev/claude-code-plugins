# Skill Validation

Validation effort should match the implementation level and risk.

| Level | Minimum Validation |
|---|---|
| L0-L1 | Manual review against 2-3 realistic prompts |
| L2 | Representative script execution |
| L3 | Build command and CLI/app smoke test |
| L4 | Persistence smoke test: create/read/update/reset or export |
| L5 | Remote config smoke test plus an unavailable-store check (it stops and reports; no fallback to another store) |

## When To Use Evals

Use evals when:

- outputs are objectively checkable
- the skill will be reused often
- the workflow has multiple steps
- regressions would be costly
- prompt triggering matters

Subjective writing or judgment skills may start with qualitative review, but still benefit from representative prompts.

## Skill-Creator Handoff

Use `skill-creator` for:

- creating the actual `SKILL.md`
- setting up eval cases
- running baseline comparisons when useful
- generating the review viewer
- improving from feedback
- optimizing trigger descriptions

Handoff package:

```md
Skill name:
Trigger description:
Implementation level:
Directory structure:
References/assets:
Scripts/CLI:
Persistence:
Validation:
Eval ideas:
Known constraints:
```

Do not call the skill complete until the selected level's operational behavior is validated.
