---
name: testcase-generator
description: Decides test perspectives from specs, source code or a PR and generates test cases in Gherkin. To keep test design from depending on one person, it makes Claude read the team's shared perspectives and style guide every time. Always use it when the user says "write test cases", "list test perspectives", "design tests for this feature", "make a test item list", "what should I test?", "review these test cases", "test design" or "QA perspectives", or in Japanese 「テストケースを作って」「テスト観点を洗い出して」「この機能のテストを設計して」「テスト項目書を作って」「何をテストすればいい？」「テストケースをレビューして」「テスト設計」「QA 観点」. Also use it when asked "how should we test this?" (「テストどうする？」) about a feature or bug-fix PR, or when deciding the scope of regression testing. Implementing test code itself (writing Playwright/vitest/pytest) is out of scope, but the case design before it happens here.
last_reviewed: 2026-09-23
review_after: 2027-03-22
---

# testcase-generator

Test design depends on one person less because of people than because of structure. The information design needs (specs, code, past bugs, the team's instincts) is scattered across different places, and **the work of cross-referencing it in your head every time is itself the tacit knowledge**, invisible from outside.

This skill brings that cross-referencing out into the open by **having the same knowledge files read every time**. So the first step is fixed.

## Files to read first, always

Read these two before generating. Starting without them yields a design made only of whatever perspectives come to mind at the moment, and the next design of the same target will not match.

1. `references/perspectives-common.md` — **where to look** (product-independent common perspectives)
2. `references/style-guide.md` — **how to write** (Gherkin format, writing steps, tags, forbidden words)

## Layer the project-specific perspectives (two-layer reference)

After the common layer, read the project-specific perspectives **on top** if they exist. Their location is defined by the "Project-specific perspectives" section of `perspectives-common.md` (under `$CLAUDE_PROJECT_DIR/.claude/knowledge/`).

You can design with the common layer alone. But **state that the specific layer is missing in the output** — "No project-specific perspectives (designed from the common layer only)". If having it and not having it look the same, readers assume "this product's know-how is already reflected".

## Make "cannot judge" writable

This procedure asks for binary verdicts again and again (in scope / out of scope, OK/NG). **Real work always produces a third state.** Forcing it into two values mixes in the lie of claiming a verdict on something that cannot be judged.

| Situation | Value to write | Example |
|---|---|---|
| The perspective structurally does not exist | **Not applicable** | "Verified by screen operation?" for a target with no screen |
| Cannot be settled without measuring | **Deferred** | The actual exception message text, values that only appear at run time |

**Always add a one-line reason to Not applicable and Deferred.** A Not applicable with no reason cannot be told apart from an excuse for avoiding the verdict.

## First, identify the kind of target

Whether the target **has a screen or not** changes the default execution-method tag and part of the self-check. Decide it first and write it in the output.

**The rule is the same as for tags**: "**what does the manual tester operate to start the case?**" If it can be started by operating a screen, it has a screen; if it can only be started by sending a request or command directly, it has none. **Do not decide by where the result is viewed** (a target where sending is via API and checking is on screen "has no screen").

**Decide per case. Do not round the whole target into one word.** It is normal for one target to mix cases that can be started from a screen and cases that cannot (handlers with no screen entry point, paths only an administrator calls, etc.).

**Write it as a tally** in the output: "Mostly has a screen (17 of 20 cases). The 3 exceptions have no screen entry point and are `@API`".
Rounding to one word erases why the exceptions are `@API`. Forcing them toward `@UI` instead **fabricates screen operations that do not exist**.

| Target | Examples | Effect |
|---|---|---|
| **Has a screen** | Web app, SPA, admin console | `@UI` by default. UI-derived self-check items apply |
| **No screen** | Backend API, batch, ETL, CLI, library | All cases being `@API` is normal. UI-derived self-check items are **Not applicable** |

Applying UI criteria to a target with no screen fails every time on items it structurally cannot meet. Do not write a false verdict to force them through.

## Input

- Path to the target's spec
- Path to the target code
- PR / pull request URL

Specs are usually missing or stale. In that case, read the code and derive behavior from what it actually does. **If you fill in the spec by guessing, mark the guessed parts distinctly in the output.**

**Even when told "there is no spec", a document equivalent to one may sit nearby** (`CLAUDE.md` / `AGENTS.md` / `README` / API docs / design notes). If you find one, read it and **always list where it disagrees with the code under "Points to confirm".** A disagreement is often where the bug is.

### What counts as correct — decided by whether an external source of truth exists

Follow the requester's instruction if there is one. Otherwise, decide by **where the source of truth is, not by the target's behavior**.

| Situation | How to derive expected values |
|---|---|
| **An external source of truth exists** (formulas, rates, rules, laws, API specs, formulas in design docs) | **Derive expected values by hand from that source.** Do not use the code's output as evidence. If they disagree, the code has the bug |
| **No external source of truth** (how the UI presents things, internal conventions, behavior settled by history) | **Treat the code as correct and pin the current behavior** (characterization). Disagreements with documents go to "Points to confirm" |

**Writing expected values while looking at the implementation copies the implementation's bugs into the tests, and green stops being evidence of correctness.** So when an external source of truth exists, always derive from it. Conversely, doubting the code even where there is no external source of truth leaves you unable to write anything.

If you cannot say which applies, **hold off on making it a case and write what is unknown under "Points to confirm".** Do not invent the correct answer.

## Steps

### 1. Draw the scope line

Read the input and decide what is in and out of scope. **Write this line as a table under `## Scope` in the output** (do not draw it only in your head). Moving on to perspective decisions while it is vague lets out-of-scope cases slip in.

### 2. Mark every perspective "In scope / Out of scope / Not applicable"

**The granularity is one row per checkbox (`- [ ]`) in §1–§4 of `perspectives-common.md`.** The §5 self-check is not a perspective, so it does not go in this table (its results go under `## Self-check`).

Do not group by heading. Grouping by heading squashes several perspectives into one row, and you can no longer trace which were looked at and which were dropped.

Give Out of scope and Not applicable a **one-line reason**. Do not read it by picking only what applies. Dropping silently leaves no record of the drop, and the hole cannot be found later.

### 3. Write test cases for each "In scope" perspective

In Gherkin. Follow the style guide for format, steps and tags. Write the cases in the user's language.

**Do not equalize the number of cases per perspective.** High-risk perspectives naturally get more cases and low-risk ones fewer. An even spread is evidence of mechanical allocation that ignored the differences between perspectives.

### 4. Add tags

Directly above each Scenario, a **priority** (`@P1`/`@P2`/`@P3`) and an **execution method** (`@UI`/`@API`). Add `@AUTO` if it is for automated tests only. Execution method and automatability are **separate axes**, so a pair like `@API @AUTO` is correct. The criteria are in the style guide's "Tags" section.

### 5. Self-check before output

Run the "Self-check after generation" in `perspectives-common.md`. Write the result item by item under `## Self-check` in the output (without evidence that it ran, "I did it" is just a claim).

- **If NG, rewrite before output**
- **Output Not applicable and Deferred as they are, without rewriting. But write the reason** (UI items for a target with no screen, expected values that cannot be settled without measuring, etc.)

If the self-check reveals a new kind of hole, **write a proposal in the output** to add it to "Lessons from past failures" in `perspectives-common.md`. Do not edit the file — it is global (shared by every project) knowledge, so pouring in a finding from the one product in front of you would affect other projects too. The user decides whether to add it.

## Output structure

**Always include this frontmatter.** Without it the checking hook skips the file, and style-guide violations go unnoticed. If you output a `.feature` file, no frontmatter is needed.

Write the section contents in the user's language. Keep the headings as below.

```markdown
---
testcase: true
---

## Scope
| Item | Content |
|---|---|
| Input used | <file path / PR> |
| In scope | <what was covered> |
| Out of scope | <what was excluded, and why> |
| Why chosen | <only if you chose the target yourself: one line on why> |
| Kind of target | Mostly has a screen / has no screen (M of N cases). Count and reason for exceptions, if any |
| Project-specific perspectives | Yes (path) / No project-specific perspectives (designed from the common layer only) |
| Spec-equivalent documents | Yes (path) / None |

## Perspective decisions
| Perspective | In scope / Out of scope / Not applicable | Reason (unless In scope) |

## Test cases
<Gherkin>

## Self-check
| Item | OK / NG / Not applicable / Deferred | Reason (unless OK) |

## Execution path
<Whether there is a path to hand these cases to execution. If not, "None" plus what is missing>

## Points to confirm
<Points guessed from behavior because there was no spec / UI terms that could not be identified /
 places where documents and code disagree / why internal-term WARNs were left and the reasoning>

## Proposed additions to the common perspectives
<Only if you found a new kind of hole. Otherwise "None">
```

Do not leave "Points to confirm" empty. Handling a target without a spec means a guess goes in somewhere. **Not presenting guesses with the same look as settled values** is this skill's premise.

Do not leave `## Execution path` empty. Test cases that were only designed have no value; **their value is settled only when they go through execution**. If there is no path to hand them over, you are piling up designs, and you should say so.

## Confirm the checking hook actually works

Enforcing the style guide's forbidden words mechanically requires the testing plugin's `testcase-lint` hook to be enabled (the plugin's `hooks/hooks.json` wires it to `Edit|Write`). **If the plugin is disabled, or only the skill was copied elsewhere, it is not wired.** The manual run below is the check: if the script is not found, the hook is not wired.

These three happen even when wired:

1. **Writing the artifact with a Bash heredoc (`cat > file <<EOF`) does not fire the hook.** The matcher is `Edit|Write` and only looks at the tool name, so writes through Bash slip past
2. **A `.md` missing the frontmatter passes completely silently** (exit 0, no output). Nothing happens even if it has violations
3. Even when the style guide cannot be read, the hook does not stop the Write

So **after writing, run the hook once by hand against the artifact and confirm with your own eyes that it produces output**:

```bash
printf '{"tool_name":"Write","tool_input":{"file_path":"<path to the artifact>"}}' \
  | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/testcase-lint.py"; echo "exit=$?"
```

**No output may mean "not checked", not "passed".** Distinguish whether targeting failed or it is truly clean. You can tell them apart by confirming a BLOCK on a temporary file with one deliberate violation.

⚠️ **Do not write the forbidden words themselves in the artifact.** If a self-check row or note **quotes a rule name**, such as "did not use '...'", that quote is detected and BLOCKed. Write it without listing the words, e.g. "no vague words". The list lives in the style guide; there is no need to copy it into the artifact.

## Set up the project-specific layer (first time only)

If you use `codebase-doctor` from the repo-setup plugin, set this up when its Check 6b reports "the specific layer is missing", or when you notice there are no specific perspectives once design starts. **The single source for the location is the "Project-specific perspectives" section of `references/perspectives-common.md`** (this file does not redefine the paths).

### What to put there

| File | Content | When needed |
|---|---|---|
| `perspectives.md` | **Where this product actually broke**. "This screen tends to break here", "this calculation goes wrong under this condition" | Always |
| `ui-terms.md` | Mapping between internal names ⇔ names shown on screen | Only for projects with a screen |
| `playbook.md` | Preconditions for running the tests (credentials, initial data, required permissions) and which order pays off | When tests exist or you move on to execution |

### ⚠️ Do not fill the contents by guessing

**Put only empty sections and an explanation of how to write them.** The perspectives come from people who watched this product break.

Filling them by guessing produces something **filled in form but empty in substance**, and it looks "set up". `codebase-doctor` only checks presence, so once filled it reports PASS. Do not create, from this side, a state where the pass mark does not guarantee the content.

For the same reason, **do not copy in the contents of the common layer (`perspectives-common.md`)**. The two-layer reference reads the common layer and layers the specific one on top, so a copy means fixing the specific side drifts from the common side. Write in the specific layer **only what the common layer does not have**.

### Template shape

```markdown
---
last_reviewed: <date placed>
review_after: <date placed + 180 days>
---

# Test perspectives specific to <product name>

Read the common perspectives (`${CLAUDE_PLUGIN_ROOT}/skills/testcase-generator/references/perspectives-common.md`)
first, then layer this on top. Do not repeat anything the common layer has.

## Where it tends to break
<!-- Add places that actually broke, with the date and symptom.
     Example: - (2026-XX-XX) Doing ... on the ... screen caused .... Check ... -->
(none yet)

## Domain-specific criteria
<!-- What counts as passing. Calculation rules, business rules, laws, etc. -->
(none yet)
```

`ui-terms.md` and `playbook.md` take the same shape (frontmatter + empty sections + an explanation of how to write them).

Once placed, **tell the user what you placed and that the contents are empty.** Placing them silently makes people think it is set up.

## What this skill does not do

- **Implementing test code** (writing Playwright / vitest / pytest) — comes after case design and depends on the project's structure
- **Running tests and judging pass/fail**
- **Detecting a missing project-specific layer** — handled by `codebase-doctor` (Check 6b) in the repo-setup plugin (this skill owns setting it up; see "Set up the project-specific layer" above)
