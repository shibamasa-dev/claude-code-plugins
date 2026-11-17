---
name: skill-planner
description: Plans a Claude Code skill before it is built. Decides whether a request should become a skill at all, picks the smallest useful implementation level, plans references / scripts / CLI / persistence / evals and how to validate them, then hands off to skill-creator (and skill-lint after it). Use before creating or upgrading a skill, when the user asks "should this be a skill?", "plan a skill", or in Japanese 「スキルにすべき？」「スキルの設計から」「スキルを作る前に計画して」「スキルの計画を立てて」.
---

# Skill Planner

Use this skill before creating or upgrading a skill when the request may become a reusable workflow, technique, project operation, decision procedure, mini app, CLI, or persistent knowledge workflow.

The goal is not to over-design. The goal is to pick the smallest implementation that makes the workflow reliable, inspectable, and reusable.

## Workflow

1. Decide whether the request should become a skill or remain a one-off task.
2. Select the minimum implementation level.
3. Identify required skill contents: `SKILL.md`, `references/`, `assets/`, `scripts/`, CLI/mini app code, SQLite, or remote persistence.
4. Plan validation: manual review, smoke test, eval cases, persistence checks, or remote sync checks.
5. If the user wants to proceed with creation or improvement, hand off to `skill-creator`.

## Read references as needed

- Read `references/implementation-levels.md` when choosing how much to build.
- Read `references/cli-design.md` when the skill may include scripts, CLI commands, a mini app, daemon, service registration, or logs.
- Read `references/persistence.md` when the skill may remember state with SQLite, files, or a remote database. **State never goes into the skill's own directory**: a plugin's skill directory is read-only and replaced on update, so state lives under `${CLAUDE_PLUGIN_DATA}` (or the user's own configured path for a standalone skill).
- Read `references/validation.md` when deciding completion criteria, smoke tests, evals, or the skill-creator handoff.

## Planning output

Return a concise plan with these fields:

```md
## Recommendation
- Decision:
- Level:
- Reason:

## Skill Shape
- Name:
- Trigger:
- Files:
- State (location under ${CLAUDE_PLUGIN_DATA}, or none):
- CLI:
- Validation:

## Handoff
- Use skill-creator:
- Notes for skill-creator:
```

If the request is clearly one-off, say so and do the task directly instead of forcing a skill.

## The chain: plan, build, check

1. **skill-planner** (this skill) produces the plan above.
2. **`skill-creator`** builds the skill, its evals, and optimizes the trigger description.
3. **`skill-lint`** checks that the finished skill is safe to distribute (no personal, company or machine-specific content). The `skill-creator-chain` hook of this plugin reminds Claude to run it after `skill-creator` finishes; if the skill is not meant to be distributed (a project-scoped skill), skip it.

## Handoff to skill-creator

When the plan is accepted and the user wants the skill created or updated, use the `skill-creator` skill for implementation, evals, improvement loops, and trigger description optimization.

Pass this information forward:

- skill name
- trigger description
- selected implementation level
- expected directory structure
- references/assets/scripts requirements
- CLI or daemon requirements
- persistence requirements (state location included)
- validation and eval plan

Do not duplicate the entire planning reference content into the new skill. Give the new skill only the operational instructions and bundled resources it needs.
