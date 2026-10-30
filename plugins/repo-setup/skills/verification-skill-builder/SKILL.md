---
name: verification-skill-builder
description: Builds a project's own real-app verification skill (`.claude/skills/verify-<app>/`) that drives the app the way its users do — a launch that isolates the run, a doctor that says whether it is safe to drive, commands run in the order of a script, evidence that is observed rather than trusted, and a cleanup that stops only what it started — plus a feature map of action → command → observed result. Use when codebase-doctor reports no real-app verification path, or for "make a verification skill for this repo", "prove this CLI works end to end", "script a way to drive the real app", or in Japanese 「検証スキルを作って」「verify スキルを作って」「実アプリで動作確認する手順をスキルにしたい」「台本どおりに CLI を叩いて確かめたい」.
last_reviewed: 2026-10-30
review_after: 2027-04-30
---

# verification-skill-builder — build a project's own real-app verification skill

Unit tests show that functions behave. They don't show that the app works when a user runs its commands one after another, with real state in between. This skill writes a project-local skill that does that: it starts an isolated copy of the app, drives it through a script, and leaves evidence behind.

The skill you write is read by an agent that has never seen the app, in the middle of another task. Write every step so it can be followed cold: real commands, real paths, no placeholders.

## 0. Decide whether the project needs one

The result is a few helper scripts and a feature map, often several hundred lines. Build it only where that weight pays off:

- **Build**: an app with several user-facing commands or screens whose correct behavior depends on running them in order (a scheduled job made of steps, a CLI that keeps state between runs, a service with multi-step flows).
- **Don't build**: a library, a single-command tool, or an app whose unit and integration tests already run the user's path end to end. Say so in one line, offer to record that decision in one line of the project's CLAUDE.md (codebase-doctor then stops proposing it), and stop.

## 1. Read the repo before asking the user

Answer these from the code, README and existing scripts. Ask the user only what the repo cannot tell you.

- **Surface**: what do users touch — CLI, web UI, API, desktop app? Pick the main one and note the rest.
- **Start**: the repo's own command for running it locally, with the env vars, ports, data directories and seed data it needs.
- **Drive**: an existing harness first (end-to-end specs, scripts the repo already uses), then a generic one (plain shell for a CLI, HTTP for a service, a browser driver for a UI).
- **Observe**: exit codes, output, files written, database rows, logs.
- **Isolate**: can state, output and config be pointed at a throwaway directory? Which commands reach production services, spend money, send messages or need someone's credentials?

If the checkout does not run as it is, fix only what belongs to the verification setup (its environment, dependencies, or the run's own config). Do not change the app's code: report the failure with its exact output and stop building. A skill written against a broken base teaches wrong steps.

## 2. Write `.claude/skills/verify-<app>/SKILL.md`

Frontmatter: `name: verify-<app>` and a `description` that names the app, its surface and when to use the skill (without frontmatter the skill is never picked up). The body has these parts, each built from what step 1 found.

**Launch** — one command that creates an isolated run:

- A fresh run directory per run. State, databases and output paths point into it.
- Tokens for production services are unset. External commands that send, spend, open things or read secrets (messaging CLIs, password managers, OS "open" helpers) are replaced by stand-ins on `PATH` that only log their arguments.
- A server is started from an empty data directory and waited on until it is usable, not just until the process answers. For a short-lived CLI there is nothing to keep running: launch only prepares the environment, and the readiness check moves into Doctor.
- If launch fails partway, it removes what it created.

**Doctor** — one read-only command that answers "is it safe and worth driving this run?" and exits non-zero when not:

- Every state and output path is inside the run directory and differs from the production locations.
- Production tokens are absent; each stand-in comes first on `PATH`.
- Required tools and versions are present; the app revision under test is recorded.

Run it before driving and whenever something looks off. Never drive a run that Doctor rejects.

**Drive** — the script: an ordered list of commands taken from this repo (real flags, real IDs, real file names). Each step saves its command, stdout, stderr and exit code. Prefer stable handles (subcommands, flags, routes, accessible names) over positions and timing.

**Evidence** — where proof goes (outside the run directory, ignored by git) and what counts as proof:

- The user's real path, not internal setters or test-only endpoints.
- The action and the state it left, checked from a second view: query the database directly, list the output directory, read the log.
- **Don't trust a dry-run or test mode by its name.** Observe what it actually did: count network connections, external processes started, and files written and where (an audit hook, `strace`, `fs_usage`, or a wrapping shim). Some dry-runs still open connections or write state.
- A test that was skipped is not a pass. Report skips with their reason as unverified.

**Cleanup**:

- Stops only what this run started, using the process IDs or session names that Launch recorded. Never kill by name pattern (`pkill -f`, `killall`): the user's own sessions and other runs can match.
- Removes the run directory and keeps the evidence.
- Compares a fingerprint of the production state taken at launch with one taken now, and exits non-zero when it changed or could not be taken.

**Helpers** — every script the skill ships is executable, and the skill body shows how to call it.

## 3. Seed the feature map

Create `features/README.md` and one file per user-facing feature, three to five to start (from commands, routes, menus or docs). Use [references/feature-map-template.md](references/feature-map-template.md).

- Every feature file uses the same fixed headings in the same order. Write them in the language the project's docs use, pick them once, and keep them identical across files so a reader always knows where to look.
- `Driving it` pairs each user action with the exact command and the result a run actually showed. Write expected results from an observed run, not from reading the code. When a later run differs, either the app changed or the map was wrong; both are worth knowing.
- **Journeys that need someone's credentials or touch production external services** (real logins, sending messages, payments, writes to shared storage) are not driven. List them under `Gotchas` as `unverified: needs <what>`.
- Never weaken a journey to make it pass. A missing precondition is a failure, with the reason in `Gotchas`.

## 4. Prove it once before handing over

Follow the new skill's own steps end to end: Launch → Doctor → Drive one mapped feature → Evidence → Cleanup.

- After Cleanup, list the evidence directory. If cleanup removed the proof, this step fails.
- Run Cleanup after failed attempts too, so they don't leave processes or directories behind.
- List every stand-in that differs from the real environment (unset tokens, a local directory in place of mounted storage, synthetic input files). Those parts stay unverified until a run in the real environment covers them.

A skill that was never run is a draft.

## 5. Report

- Path of the new skill and its files
- The proof run: its ID, each step's exit code, where the evidence is, and that it survived cleanup
- Stand-ins and journeys left unverified
- Bugs in the app found along the way, reported only (this skill does not change the app under test)

## Boundaries with other skills

| To do this | Use |
|---|---|
| Find out whether a repo has a verification skill at all | `codebase-doctor` (Check 17) |
| Design test cases and their perspectives | `testcase-generator` (testing plugin) |
| Launch the app once to look at a change | the app's own run command; this skill is for a repeatable, scripted proof |
