# lint

English | [日本語](README.ja.md)

Linters for artifacts such as skills. Currently only `skill-lint`.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install lint@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `skill-lint` | Checks whether a skill is safe to distribute to anyone. Run it with `/lint:skill-lint <skill directory>`. The question it asks: "Would this skill still work if someone at another company installed it on another machine, and what would it reveal about you?" A deterministic `lint.py` (generic regexes only) finds email addresses, absolute home paths and paths that look like personal directories, tailnet hosts, private issue numbers, decision history, and runtime data under the skill. Personal names, company and client names, dependencies on private bots or repos, and environment-specific steps are judged by an agent reviewer, using hints it collects from the environment (`whoami`, git `user.name` / email, the gh login, the host name) and the lint results. Only reviewer findings whose quote appears verbatim in a line are kept, and they are reported by category with suggested fixes. It asks before fixing anything |

## Hooks

| Hook | When | What it does |
|---|---|---|
| skill-creator-chain | After Skill | When the skill that ran is skill-creator (including namespaced names), tells Claude to run skill-lint on the skill's directory once the skill is created or updated. Project-scoped skills (`.claude/skills` inside a repo) are excluded. Does nothing for other skills |

## Proper names

There is no denylist of names. A file that collects names would itself be a leak and would need upkeep. Proper names are judged by the reviewer from hints it collects from the environment at run time, and from context.

## Requirements

- `python3` (standard library only)
- Optional: `gh` (the reviewer uses your gh login as a hint), `gitleaks` (handles secret scanning; reported as `skipped` if missing)
- Eval group B (`scripts/run_reviewer_eval.py`) needs the `claude` CLI
