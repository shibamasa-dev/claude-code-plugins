# Repository structure rules (docs/, scripts/, temporary files)

> The guards plugin's repo-structure-guard hook reads the `<!-- guard:… -->` blocks in this file before each Write. It blocks creating a new .md directly under docs/ and a new script directly under scripts/.
>
> **This is a sample. The copy inside the plugin is never read by the hook.** To use it, copy it to one of the locations below and adapt it to how you work.
> - Per repo: `<repo>/.claude/rules/repo-structure.md` (commit it to share with the team; Claude also reads it as a rule)
> - All your repos: `~/.claude/rules/repo-structure.md`
>
> If both exist, the repo's copy wins. If the environment variable `REPO_STRUCTURE_SPEC` is set, only that file is used. To change a value, edit one line of a block; the hook's behavior and its deny message change together.

## docs/ structure

- **Don't put .md files directly under docs/.** The only exception is `docs/README.md` (the index: one line per item saying what is where; no content).

<!-- guard:docs-allow-filenames -->
- README.md
<!-- /guard:docs-allow-filenames -->
- **Split subfolders by kind.** Create **only the ones you need** from the standard set (don't dig empty folders in advance):
  - `spec/` — specs and design (what to build, how to build it) [overwrite: always the current truth]
  - `adr/` — decision records (why we did it) [append: `YYYYMMDD_` prefix]
  - `research/` — investigations, experiments, measurement reports (what we learned) [append: `YYYYMMDD_` prefix]
  - `ops/` — operating procedures, runbooks (how to run it) [overwrite]
  - `reference/` — external contracts, APIs, schemas (what is authoritative) [overwrite]
- **When unsure, ask one question**: the block below is the authoritative standard set and the question for each folder (the hook's deny message is built from it too).

<!-- guard:docs-subfolders -->
- spec: what to build and how
- adr: why
- research: what we learned
- ops: how to run it
- reference: what is authoritative
<!-- /guard:docs-subfolders -->
- **Don't create README.md in subfolders.** Keep the index in `docs/README.md`. If a subtree gets deep enough to need guidance, put a **CLAUDE.md** there instead of a README (agents read it automatically for that directory scope).
- **Don't split by phase.** Projects loop (research → requirements → build → develop → test → research → improve → …), so phase folders like `01_research/` break on the second lap. Splitting by kind is orthogonal to phases: each loop's output lands in an append folder (research, adr = kept as history) or an overwrite folder (spec, ops, reference = updated to the current truth). 0→1 starts with research plus a few specs; in 1→100, when spec grows, split it by topic (e.g. `spec/auth/`) and add a CLAUDE.md for navigation where it gets deep.
- Large topics that don't fit the standard set (e.g. `accounting/`) may sit alongside them, but register each with one line in `docs/README.md`.
- **Don't retroactively refactor existing repos.** Apply this to new documents. Existing documents can be moved when you touch them (watch for broken links).

## The boundary between docs and code (no double bookkeeping)

- **Don't write in docs what can be read mechanically from the code.** The code is the source of truth: DB schema = migrations/DDL, types and API signatures = type definitions, settings and command lists = code/--help, directory layout = ls. In docs, write at most a one-line pointer (e.g. "the schema lives in `migrations/`"). If you never write a copy, nothing can go stale.
- **Write in docs only what doesn't show in the code**: why (adr) / requirements, intent, scope (spec) / flows and sequences across components (spec) / investigations and measurements (research) / operations where order, timing and caveats are the point (ops).
- **One question**: "Can you tell this exactly by reading the code?" YES → don't write it.

## scripts/ structure

- **Don't put scripts directly under scripts/.** Split by feature or domain into subfolders (e.g. `scripts/scheduler/`, `scripts/launcher/`, `scripts/deploy/`). Extensions treated as "scripts":

<!-- guard:script-extensions -->
- .sh
- .py
- .js
- .ts
- .mjs
- .rb
- .zsh
- .bash
<!-- /guard:script-extensions -->

- **Exception: the skill layout.** A skill correctly keeps its scripts directly under `<skill>/scripts/` (the `skill-creator` layout), so it is exempt from this rule. That's a different matter from splitting the repo's top-level `scripts/` into feature subfolders.

<!-- guard:exemptions -->
- path-component-skills: directly under a `scripts/` whose path from the repo root has a `skills` component (a skill correctly keeps scripts directly under `<skill>/scripts/`; doesn't apply to the checkout location or to docs/)
- sibling-skill-md: when the parent directory of `scripts/` has a `SKILL.md` (skills aren't always under `skills/`)
<!-- /guard:exemptions -->

  Removing an ID from the block turns that exemption off (the hook reads the IDs to decide).
- When entry points and internal helpers start to mix, move the helpers to `lib/` or mark them with a `_` prefix.
- If guidance is needed, use a CLAUDE.md rather than a README (same policy as docs).

## Temporary files

- Put them where the system prompt's scratchpad instructions say (only deliverables you intend to commit may be created inside the repo). The following adds what the prompt doesn't cover.
- Gitignored paths (`.claude/state/` etc.) are **places for persistent state**, not for temporary files. Don't keep temporary files in the repo "because it's gitignored".
- Before committing, check with `git status` that no untracked leftovers remain.
