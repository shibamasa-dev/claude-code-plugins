# Feature map template

Copy these two shapes into `.claude/skills/verify-<app>/features/`. Replace every `<...>` with what a run showed. Keep the headings fixed and identical across files; translate them once into the language the project's docs use if that is not English.

## `features/README.md`

```markdown
# <app> verification map

The maintained recipes for checking <app> the way its users run it. Read this file first, then the feature file for the journey you need.

## Baseline

- Launch: `<launch command>` → prints the path of the run's env file
- Doctor: `<doctor command>` → every line `OK`, exit 0. Do not drive on anything else
- Evidence: `<evidence directory>/<run id>/`
- Cleanup: `<cleanup command> <env file>` → exit 0, evidence kept

## Proof rules

- Each step keeps its command, stdout, stderr and exit code
- A change of state is confirmed from a second view (`<db query or listing command>`)
- Network, external processes and file writes are counted, not assumed from a flag name
- A skipped path is reported as unverified with its reason, never as passed

## Features

| Feature | File | Driven |
|---|---|---|
| <feature> | `<feature>.md` | yes / unverified: needs <what> |
```

## `features/<feature>.md`

```markdown
# <Feature name>

<One paragraph: what the user gets from this feature.>

## Sub-features

- `<id>` <one line per behavior>

## How users reach it

- <command, menu or route a user actually uses>

## Driving it

Preconditions: <state the run needs; Doctor passed>

- **<action>** — `<exact command>` → <observed result: exit code, output line, row, file>
- **Second view** — `<query or listing>` → <observed state>

## Gotchas

- <trap that wastes or invalidates a run>
- unverified: needs <credentials / production service / device>
```
