# Skill Implementation Levels

Choose the smallest level that makes the workflow reliable and repeatable.

| Level | Use When | Contents | Completion Criteria |
|---|---|---|---|
| L0. Guidance only | The workflow is mostly judgment, writing style, checklist, or tool order | `SKILL.md` | Trigger description and procedure are reusable |
| L1. References/assets | The workflow needs examples, schemas, templates, prompts, or static knowledge | `SKILL.md`, `references/`, `assets/` | The model can load only the relevant reference files |
| L2. Scripts | The workflow has deterministic, repetitive, or error-prone steps | `scripts/` plus instructions | At least one script path works manually |
| L3. CLI/mini app | Users or agents should run a reusable local command, parser, generator, evaluator, or app | Self-contained code (no state) in the skill directory | Build/run/smoke test commands are documented and pass |
| L4. Local persistence | The skill needs local history, indexes, caches, preferences, queues, or eval results | SQLite or local files in the state location (`persistence.md`) | Schema, update path, reset/export behavior are documented |
| L5. Cross-environment persistence | State must work across machines, sessions, or deployments | A remote store (Postgres, Supabase, Turso, etc.) | Setup, auth, unavailable-store behavior, and data boundaries are documented |

## Escalation Heuristics

- One-off task: do it directly.
- Reusable decision procedure or workflow: L0.
- Durable examples, specs, schemas, templates, or reference docs: L1.
- Repeated helper code or deterministic transforms: L2.
- User-facing or agent-facing command with repeated operations: L3.
- Local state that improves future runs: L4.
- Shared state across environments: L5.

When uncertain, start lower and leave an upgrade path.

## Skill Directory Boundary

Keep code (scripts, CLI tools, build configuration, mini-app source) self-contained in the skill directory. Keep state elsewhere. In a plugin the plugin root is replaced on update, so anything stored there is lost.

Recommended layout:

```text
skill-name/
├── SKILL.md
├── scripts/
├── src/
├── references/
├── assets/
├── evals/
├── package.json / pyproject.toml / Cargo.toml / etc.
└── README.md
```

Rules:

- Do not scatter skill implementation files into Claude's user configuration directory or unrelated project directories.
- Write state (databases, caches, logs, run records) to the state location, never into the skill directory: for a plugin skill `${CLAUDE_PLUGIN_DATA}`, for a standalone skill a path the user chooses (see `persistence.md`). Generated output of a plugin skill (dependencies, build output) also goes under `${CLAUDE_PLUGIN_DATA}`; a standalone skill may build in its own directory (see `cli-design.md`). Temporary work goes to a temp directory.
- Document install/build/run commands when dependencies are needed.
- Prefer small deterministic scripts before creating a larger CLI or app.
