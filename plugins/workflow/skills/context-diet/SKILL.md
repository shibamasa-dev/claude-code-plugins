---
name: context-diet
description: Measure and reduce the context loaded at the start of every session. Covers two layers — (A) always-loaded text (CLAUDE.md, rules, memory index), measured with measure.py and compressed only when over threshold; (B) the injected layer (MCP connectors, skills list), inventoried with inventory.py and trimmed via deniedMcpServers / skillOverrides in the project's .claude/settings.json. Use when the user says "reduce context", "startup load is heavy", "CLAUDE.md is too big", "is memory bloated?", "measure always-loaded context", "turn off MCP servers/skills this project doesn't use", "clean up connectors", or in Japanese 「コンテキスト減らして」「初期ロード重い」「CLAUDE.md 重い」「メモリ肥大してない？」「常時ロード計測」「このプロジェクトで使わない MCP/スキルを切りたい」「コネクタ整理」. Detection is mechanical, judgment is the LLM's, and the final target list always needs user approval.
last_reviewed: 2026-09-06
review_after: 2027-03-05
---

# context-diet — measure and cut the startup load

Two kinds of things are loaded before a session starts. **Looking at only one of them leads to a misdiagnosis.**

| | Phase A: always-loaded text | Phase B: injected layer |
|---|---|---|
| Contents | CLAUDE.md, rules, memory index | MCP tool name list, skills list, MCP server instructions |
| How it grows | **Gradually**, as text is added | **Everything is there from the start** (including things unrelated to the project) |
| Trigger | **Threshold-driven** (only when exceeded) | **One inventory per project** |
| Output | Compress or move files | Project `.claude/settings.json` |

Don't act on gut feeling. "Many files = heavy" is a misdiagnosis (files read only at recall time cost nothing on every session). Conversely, **Phase B can be bloated even when Phase A is ok**. Don't use one phase's verdict as the conclusion for the other.

---

# Phase A — always-loaded text

## A-1. Measure (mechanical, always safe)

```bash
python3 scripts/standing/measure.py --project <project root>   # defaults to cwd
```

- Scope: global CLAUDE.md / `~/.claude/rules/*.md` (only those without frontmatter `paths:`) / project CLAUDE.md, AGENTS.md, `.claude/CLAUDE.md` plus one level of `@import` / `.claude/rules/` / memory index MEMORY.md
- Output: JSON (total KB, token estimate, index line-length distribution, index ↔ body consistency, broken `[[links]]`, top files)
- exit 0 = ok / 1 = over threshold (default thresholds: always-loaded total 130KB, index average line length 100 chars. Change with `--max-standing-kb` / `--max-index-avg`)
- Local reads only, no auth needed, runs inside the sandbox

**If ok, finish Phase A with a one-line report.** Grooming within the threshold is a waste of time (criteria in `references/criteria.md`). **But don't end the conversation here — move on to Phase B.**

## A-2. Grooming (LLM judgment, only when over threshold)

Follow criteria 1–9 in `references/criteria.md`. Key points:

- **Only three levers work on the text layer**: compress / move to a non-auto-loaded path (e.g. `~/.claude/reference/`) and leave a pointer / turn rules into `paths:` globs. **Splitting into rules/ does not reduce anything** (it is still auto-loaded)
- **Keep the substance of operating rules.** Long history and examples become "date + one-line conclusion". Keep authoritative sources such as approval dates
- **Rules that moved to a mechanical enforcement point such as a hook** may be compressed to a one-line pointer
- **One hook per index line.** If all lines routinely exceed 80 chars, rewrite the index
- **Delete only "finished project state" and broken references.** Don't merge duplicate clusters
- **Be careful with promotion** (it undoes the slimming)

## A-3. Verify (required)

1. Back up with `cp` before editing, and confirm the copy is byte-identical before you edit
2. After compressing: heading parity (`diff <(grep -E "^#{2,3} " before) <(grep -E "^#{2,3} " after)` shows zero lost headings)
3. Index: rerun `measure.py` and confirm zero consistency breaches (missing_from_index / missing_bodies / broken_wiki_links)
4. Include before/after KB in the report

---

# Phase B — injected layer

Lever specs, verification commands, and the limits of verification are all in **[references/harness-levers.md](references/harness-levers.md)**. **Always read it before starting Phase B.**

## B-0. Absolute rule

> **Always get user approval before finalizing what to cut. Never write settings.json without confirmation.**

What is needed depends only on the project's contents and the user's intent. The agent's guesses are not reliable.

- Propose **by group**: ① claude.ai connectors (`deniedMcpServers`) ② personal skills (`skillOverrides`)
- **Get a yes/no for each group.** Don't settle for "is all of this OK?"
- **Don't include plugin or account-side skills in the proposal.** `skillOverrides` has no effect on them (harness-levers.md). Dropping them means disabling the whole plugin via `enabledPlugins`, which affects every project, so raise it as a separate topic
- **When in doubt, keep it.** A wrong cut goes unnoticed — a skill just disappears from the list, and a connector just looks like a missing tool
- If the user names specific things to remove, apply those first

## B-1. Inventory (mechanical, collection only)

```bash
python3 scripts/injected/inventory.py --project <project root>
python3 scripts/injected/inventory.py --no-connectors   # fast, offline
```

- Output: connector list (name, status, already denied or not) / skills list (name, description bytes, already overridden or not) / current `.claude/settings.json` settings / totals
- **It makes no keep/drop decisions.** The LLM and the user decide afterwards
- It calls `claude mcp list`, so expect a wait for health checks (a few seconds to tens of seconds)

**What inventory.py does not show** (also stated in `not_enumerable`):
- Account-side skills (`small-business:*` / `anthropic-skills:*` / `design:*`, etc.) — not on disk
- Built-in skills (`code-review` / `simplify` / `schedule`, etc.)

**Pick these two up from the agent's own skills list.**

## B-2. Classify and present to the user

Read the project's contents (README, CLAUDE.md, languages, dependencies) first, then sort each candidate into "used / not used / can't tell". Present **with byte counts**, by group.

Rules of thumb:

- **Connectors**: keep those that the project's operating docs (CLAUDE.md, AGENTS.md) explicitly require. "Might be handy" goes on the drop side
- **Skills**: never touch the project's own `.claude/skills/`. Skills that are active in other projects but never trigger in this one become `user-invocable-only` (they still work when called as `/name`)
- **The default is `user-invocable-only`.** Use `off` only for things you can say will never be used again

## B-3. Generate and apply

Build `.claude/settings.json` from the approved groups only.

- **Don't break existing keys (`hooks`, etc.).** Read the existing JSON and only add `deniedMcpServers` / `skillOverrides`
- Back up with `cp` before writing, and confirm the copy is byte-identical
- In `auto` permission mode the classifier may deny the write. If so, write the finished file to the scratchpad and give the user a `cp` command (don't try to work around it; details in harness-levers.md)

## B-4. Verify (required)

```bash
claude mcp list                                     # the dropped connectors are gone
claude mcp get "<connector you kept>"               # the kept side is alive
claude -p --model haiku 'Output ONLY JSON: {"<dropped skill>":<listed?>, "<kept skill>":<listed?>}' < /dev/null
```

- **Always use a control.** "The dropped side is false" alone can't rule out that it was never listed. Confirm in the same run that **the kept side is true**
- **Then check the round trip.** The model hallucinates on that yes/no. For each item that came back false, **remove the override and confirm it returns to true**. Don't call a one-way observation "proven"
- **`skillOverrides` works only on personal skills** (not on plugin or account-side skills; see harness-levers.md). Don't leave ineffective keys in the settings — they look like they work but do nothing
- Some things can't be verified headless (`name-only`, account-side skills). **Report them explicitly as unverified**
- For the final check, ask the user to run `/context`. Slash commands can't be run from a non-interactive session

## B-5. Guide the user through operations only they can run

This skill's steps include **things the agent cannot run**. Don't silently give up or brush them off with "please do this later". **Give them in copy-paste form, and state at the end of the report that they are waiting on the user.**

| Operation | Who | Why the agent can't |
|---|---|---|
| `/mcp disable <server>` | User | Slash commands can't be run from a non-interactive session. The only way to drop a built-in MCP |
| `/context` | User | Same as above. The only way to measure the fixed cost |
| `/reload-skills` `/reload-plugins` | User | Same as above. Needed to apply setting changes immediately |
| Writing `.claude/settings.json` | Depends | In `auto` permission mode the classifier denies it. If denied, hand over the finished file and a `cp` command |
| Connector OAuth | User | The auth flow needs interaction |

**Guidance template** (always include these 5 points):

1. **What the command does**, in one line
2. **A copy-paste block** (if there are several, list them all; don't dole them out one by one)
3. **Scope** — project only, or affects everything
4. **How to undo it**
5. **What to check after running it**

Example:

```
/mcp disable claude-in-chrome
/mcp disable computer-use
```
- Disables the built-in MCP servers for this project only (17.1k tokens less in total)
- **Project scope.** Recorded in the projects entry of `~/.claude.json`; does not affect other projects
- Undo with `/mcp enable <name>`
- Success if MCP tools shrink in `/context` after running it

## ⚠️ `.claude/settings.json` changes with the branch

If it is tracked by git, **the diet turns on/off the moment you switch branches** (the settings exist only on the branch where you added them). Hitting this right after applying leads to the misdiagnosis "it stopped working".

- To make it permanent, **merge to main early** (later branches inherit it)
- If you only want it stable across branches, put it in `.claude/settings.local.json` (not tracked by git). It can't be shared, though, and a running session may write back to it
- **If it "suddenly stopped working" during verification, suspect `git branch --show-current` first**

---

## Report format

```
Phase A: <total KB> / <ok|over>   (before→after only when over)
Phase B: connectors <before>→<after>, skillOverrides <count>
Verified: <facts confirmed by verification commands>
Unverified: <things that couldn't be measured headless>
Next: restart → confirm with /context
```

Don't present estimates and measurements in the same voice. Write "estimate" for anything that was only counted.

## Scheduled runs

Run **Phase A only** monthly (bloat is slow). Register a thin task with the scheduler: "run measure → if ok, close with one line → groom only when over". **Don't schedule Phase B** — once per project is enough; redo it only when new connectors or skills are added.

## Evals

```bash
python3 evals/run_evals.py   # generates fixtures automatically and verifies; zero manual steps
```
