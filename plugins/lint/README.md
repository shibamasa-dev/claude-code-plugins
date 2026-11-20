# lint

English | [日本語](README.ja.md)

Tools for making skills well: `skill-planner` plans a skill before it is built, and `skill-lint` checks it afterwards. The chain is plan (`skill-planner`) → build (`skill-creator`) → check (`skill-lint`).

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install lint@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `skill-planner` | Plans a skill before it is built. Decides whether a request should become a skill at all, picks the smallest useful implementation level (guidance only → references → scripts → CLI → local or remote persistence), plans references, scripts, state location and validation, and hands the plan to `skill-creator`. State is planned under `${CLAUDE_PLUGIN_DATA}` for a plugin skill, or at a path the user chooses for a standalone skill, never inside the skill directory. Triggers when you ask whether something should be a skill or want a skill planned |
| `skill-lint` | Checks whether a skill is safe to distribute to anyone. Run it with `/lint:skill-lint <skill directory>`. The question it asks: "Would this skill still work if someone at another company installed it on another machine, and what would it reveal about you?" A deterministic `lint.py` (generic regexes only) finds email addresses, absolute home paths and paths that look like personal directories, tailnet hosts, private issue numbers, decision history, and runtime data under the skill. Personal names, company and client names, dependencies on private bots or repos, and environment-specific steps are judged by an agent reviewer, using hints it collects from the environment (`whoami`, git `user.name` / email, the gh login, the host name) and the lint results. Only reviewer findings whose quote appears verbatim in a line are kept, and they are reported by category with suggested fixes. It asks before fixing anything |

## Hooks

| Hook | When | What it does |
|---|---|---|
| skill-creator-chain | After Skill | When the skill that ran is skill-creator (including namespaced names), tells Claude to run skill-lint on the skill's directory once the skill is created or updated. Project-scoped skills (`.claude/skills` inside a repo) are excluded. Does nothing for other skills |
| design-lint | After Edit or Write | When `DESIGN.md` is edited, runs `npx -y @google/design.md@latest lint <path>` and returns the findings. If lint cannot run (no network, `npx` fails), says it is unverified instead of passing silently. Does nothing for other files |

## Proper names

There is no denylist of names. A file that collects names would itself be a leak and would need upkeep. Proper names are judged by the reviewer from hints it collects from the environment at run time, and from context.

## Configuration

### Where files go

| What | Where |
|---|---|
| skill-lint's working files (`lint.json`, `review.txt`, `review.json`) | the session scratchpad, or a `mktemp -d` directory removed after the report |
| The reviewer evals (`run_reviewer_eval.py`) | `mktemp -d` directories; `--keep <dir>` keeps the output there |

It keeps nothing in its plugin data directory, so uninstalling removes none of these files.

## Requirements

- `python3` (standard library only)
- `design-lint`: `npx` (needs network access)
- `skill-creator` (from another marketplace) is optional: `skill-planner` hands its plan to it when installed, and otherwise the plan is built directly
- Optional: `gh` (the reviewer uses your gh login as a hint), `gitleaks` (handles secret scanning; reported as `skipped` if missing)
- Eval group B (`scripts/run_reviewer_eval.py`) needs the `claude` CLI. The eval scripts are for the maintainers: they read the eval set under `evals/`, which is kept locally and not published

## Tests

```bash
bash plugins/lint/tests/run-all.sh
```
