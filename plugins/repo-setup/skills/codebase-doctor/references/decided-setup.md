# Decided setup section

The one block of CLAUDE.md that codebase-doctor writes (Step 1a-start) and later shrinks. Everything about writing, finding and removing it is here.

## Template

The keys are fixed, so removal works per key:

```markdown
<!-- codebase-doctor:decided-setup -->
## Decided setup

Recorded by codebase-doctor at project start. A line leaves once the repo's own files state it.

- Purpose: <from question 1>
- Constraints: <from question 4, or "none">
- Language / runtime: <choice> — <reason>
- Package manager: <choice> — <reason>
- Framework: <choice> — <reason>
- Test runner: <choice>, watch mode off — <reason>
- Lint / format: <choice> — <reason>
- CI: <choice> — <reason>
- Hosting: <choice> — <reason>
<!-- /codebase-doctor:decided-setup -->
```

- **Omitted bullets**: Framework when the project type needs none; Hosting when the answer to question 2 was "The user's own machine" or "Not decided yet" (no repo file could ever state it, so the line would never leave)
- **Size when first written**: 13–15 lines from the opening marker to the closing marker inclusive (15 in full, one less per omitted bullet). Later runs shrink it below that; that is intended
- **No CLAUDE.md**: create it holding only the block and a final newline. **AGENTS.md but no CLAUDE.md**: create CLAUDE.md with `@AGENTS.md`, a blank line, then the block; never edit AGENTS.md
- **Existing CLAUDE.md**: append at the end. Add a `\n` only if the file does not end in one, then one blank line, then the block and a final `\n`. Nothing before the original end of file changes, so the hand-written text stays a byte-identical prefix
- **The skill's own bytes** are the block (opening marker to closing marker) plus the one separating blank line it wrote before it. It never changes any other byte of CLAUDE.md
- **Find the section only by its markers**, never by heading text. At most one section exists

## Removal on later runs

Check each bullet against its evidence:

| Key | Proposed for removal when the repo states the same value in |
|---|---|
| Purpose, Constraints | never — code cannot state them |
| Language / runtime | a manifest of that language, plus the runtime (see below) |
| Package manager | that manager's lock file tracked in git, or a `packageManager` field naming it |
| Framework | the manifest's dependencies |
| Test runner | a command wiring the runner (Check 16) **and** watch mode off in its config or in the command |
| Lint / format | the tool's config file (Check 16's list), covering every job the line names |
| CI | a workflow file that runs the named steps |
| Hosting | the platform's deploy config (`wrangler.toml`, `vercel.json`, `fly.toml`, `Dockerfile`, …) |

**Every part of the value must be stated.** A partly stated line stays:

| Line value | Stated by | Not stated by |
|---|---|---|
| TypeScript on Cloudflare Workers | a `typescript` dependency or `tsconfig.json`, **and** `wrangler.toml` or `@cloudflare/workers-types` | `package.json` with `typescript` alone (that says Node.js) |
| TypeScript on Node.js | `package.json` with a `typescript` dependency or `tsconfig.json`, **and** a positive Node.js signal: `engines.node`, `@types/node`, or a script that runs `node` / `tsx` / `ts-node` | a browser-only TypeScript project (Vite or similar, no Node.js signal); `tsconfig.json` without `package.json` |
| Biome (lint and format) | `biome.json` where neither `linter.enabled` nor `formatter.enabled` is `false` (both default to on) | `biome.json` with `formatter.enabled: false` (states lint only) |

- **Same value stated** → propose removing the line. All removals of one run form **one grouped Step 6 proposal** naming the evidence ("Shrink Decided setup: remove 3 lines now stated by package.json, pnpm-lock.yaml, eslint.config.js"). Never remove a line without approval
- **A different value stated** (the section says pnpm, the tracked lock file is `package-lock.json`) → keep the line, report `[WARN]` under Check 1 ("Decided setup contradicts the repo: Package manager"), and let Step 6 ask whether to keep or remove it
- **Only manifests and config files are evidence.** Prose elsewhere in CLAUDE.md removes nothing
- **Lines the user edited or added inside the markers**: a bullet with a known key is compared using its current value — the edit is the current decision. Any other line (free text, a bullet with an unknown key) is never removed or rewritten, and keeps the section alive
- **Empty section**: once no bullet and no user line would remain, the proposal removes the skill's own bytes — the block and the one separating blank line that the skill added — and nothing else. The file itself is never deleted, even when what remains is only whitespace or `@AGENTS.md` (the skill cannot tell whether it created that text); Check 1 then rates the file as usual
- **Broken markers** (an opening marker without a closing one, or more than one section): edit nothing, report `[WARN]` under Check 1, and ask the user to fix the markers

## States

| Repo | Section | This run |
|---|---|---|
| only docs and repo metadata | none | project start: ask → propose → write on Adopt |
| only docs and repo metadata | present | ask nothing; use the section as the stack; Check 16 proposes what it names |
| anything else tracked (manifest or not) | present | the section is the stack; inference fills only the areas it has no line for; removal check above. With nothing to remove, note "Decided setup: N lines still needed" and propose nothing |
| anything else tracked | none | normal audit (stack from manifests, else `[inferred]`), no questions, nothing written |
| any | broken markers | not project start; edit nothing; `[WARN]` under Check 1 |

A user who chose "Don't record", or a run that could not ask, leaves no trace, so the next run in a still-empty repo asks again. There is no hidden state file.
