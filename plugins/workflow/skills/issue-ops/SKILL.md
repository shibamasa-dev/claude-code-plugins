---
name: issue-ops
description: Procedure to read before acting whenever asked to create, close, update, split, or tag GitHub issues. Covers the operating rules (Issue Fields values, sub-issue hierarchy, body vs. comments, the `## Result` and `## Notes for next time` sections at close, the Arch Review gate, choosing dates and Priority, acceptance-criteria format and when to use Gherkin, deciding whether a leftover becomes an issue or a PR stack layer). Go through this skill before calling issue_write / gh issue create|edit|close directly. Use for "make an issue", "close it", "split into parent/child issues", or in Japanese 「作って」「issue にして」「issue 化して」「起票して」「タスク化して」「閉じて」「クローズして」「完了にして」「更新して」「親子に分けて」「親 issue / 子 issue / ゴール issue に分けたい」「大きい仕事を issue に割りたい」「Recurrence 付けて」「Arch Review にして」.
last_reviewed: 2026-10-06
review_after: 2027-03-21
---

# issue-ops — GitHub issue operations

> This is the source of truth for issue operating rules. CLAUDE.md only needs the gist: "when a task comes up, make an issue; the procedure is in this skill."

### Overview

When a task comes up, **create a GitHub issue, and in organizations with Issue Fields, set the metadata with them**. If the project board auto-adds issues, don't touch the Projects API. **GitHub MCP is the default for operations** (in organizations with Issue Fields, use organization-level Issue Fields for metadata; don't use ProjectV2 GraphQL). **But in environments where MCP `issue_write` shows an approval form, don't wait for the form; do it directly with `gh` + GraphQL** (see "When MCP shows an approval form" below. Creating, updating, and closing issues needs no user approval).

For organization values (GitHub organization, default issue repo, Issue Fields table, project board), use injected text in the session context headed "Organization settings" (or 「組織設定」 in Japanese) if present. Otherwise use the project's CLAUDE.md, and if that has none, ask the user. Don't fill them in by guessing. Take the target repository from the context (github_repo etc.); if unknown, use the default repo from the organization settings.

### Issue Fields (only in organizations that have them; organization-level; shared by all repos)

Below are the operating rules for field names and the meaning of values. For field IDs and per-organization differences, see the organization settings (Issue Fields only work in organization-owned repos).

| Field | Type | Values |
|-----------|-----|-----|
| Priority | single_select | Urgent / High / Medium / Low |
| Start date / Target date | date | YYYY-MM-DD |
| Effort | single_select | High / Medium / Low (optional) |
| Recurrence | single_select | Weekly / Monthly / Quarterly / Semiannual / Yearly (unset = one-off. Always set it on recurring tasks) |
| Arch Review | single_select | Pending / Approved (unset = not subject to review) |
| Verification | single_select | Not needed / Pending / Verified (unset = treated as Not needed). Shows whether acceptance criteria that can only be checked in the real environment remain |

In MCP, **specify fields by name** (single_select uses `field_option_name`, date etc. use `value`; check definitions with `list_issue_fields`). For state and classification metadata, prefer an Issue Field over labels (one field = one axis, minimal options, limit 25 per organization). **Setting and reading values works in MCP. Creating or changing field definitions needs `admin:org`, so do it in the GitHub UI**.

### Creating an issue (one MCP `issue_write` call)

```
issue_write(method: "create", owner: "<org>", repo: "<repo>", title: "...", body: "...",
  issue_fields: [
    { field_name: "Priority",    field_option_name: "Medium" },
    { field_name: "Start date",  value: "2026-07-15" },
    { field_name: "Target date", value: "2026-07-31" }
  ])
```

- Update with `method: "update"` + `issue_number`. Read with `issue_read`'s `field_values`; list and filter with `list_issues(field_filters: [...])`.

### When MCP shows an approval form (use gh + GraphQL directly)

In environments where `issue_write` returns "interactive form has been shown", such as the Code tab of the Claude desktop app, nothing happens until the user clicks Submit (forms just pile up, and an issue you think you created may not exist. Even after Submit, Issue Fields may not be set). **Once a form has appeared, switch all issue operations in that session to the methods below** (reading with `issue_read` shows no form, so it can stay on MCP).

| Operation | Command |
|---|---|
| Create | `gh issue create --repo <o>/<r> --title "…" --body-file <file>` (write the body to a file first) |
| Update body/title | `gh issue edit <n> --repo <o>/<r> --body-file <file>` |
| Comment | `gh issue comment <n> --repo <o>/<r> --body-file <file>` |
| Close | `gh issue close <n> --repo <o>/<r> --reason completed` (after writing `## Result` in the body) |
| Parent/child (sub-issue) | `gh api -X POST repos/<o>/<r>/issues/<parent>/sub_issues -F sub_issue_id=<child's .id (number, not node_id)>` |
| Set Issue Fields | GraphQL `setIssueFieldValue(input:{issueId:<issue node_id>, issueFields:[{fieldId:<id>, singleSelectOptionId:<id>}, {fieldId:<id>, dateValue:"YYYY-MM-DD"}]})` |
| Read Issue Fields | GraphQL `repository(…){issue(number:N){issueFieldValues(first:10){nodes{… on IssueFieldSingleSelectValue{name field{… on IssueFieldSingleSelect{name}}} … on IssueFieldDateValue{value field{… on IssueFieldDate{name}}}}}}}` |

- Look up field and option IDs with `organization(login:"<org>"){issueFields(first:20){nodes{__typename … on IssueFieldSingleSelect{id name options{id name}} … on IssueFieldDate{id name}}}}` (don't guess IDs).
- After setting, confirm the values with the read query above.

### Writing acceptance criteria (with or without Gherkin)

Acceptance criteria go **inline in the body** (they define what is correct, so they don't change until close). **Use Gherkin (Given/When/Then) only for issues that change behavior; otherwise use bullet points.**

30-second test: **Can you write at least 2 lines of observable real values (column names, flags, counts, file names) under Then?** If not, use bullets.

| Use Gherkin | Keep bullets |
|---|---|
| Behavior changes whose input and expected output can be written as real values | Docs, config, dependency updates, refactors (Then can only say "nothing changes") |
| Covering branches is the point (INSERT/UPDATE, normal/stale/conflict/empty/encoding) | A single normal path. Three bullet lines are enough |
| Reproduction conditions in a bug report (real data and real state in Given) | `Arch Review: Pending` (behavior not settled yet; writing it first makes you feel it is decided) |
| Acceptance criteria in a delegation seed (the implementing agent reads it with zero background) | The topic is a timeline or interaction between several actors → that is `sequenceDiagram` territory |

How to write it (a shape whose syntax prevents "all tests green even though only the UPDATE path misses an update"):

```gherkin
Scenario Outline: Importing a slip file sets the print-target flag
  Given order number <order number> is <existing state>
  When  slip file <file name> goes through the import
  Then  the print-target flag becomes '1'
  And   <other update columns defined in the spec> are updated

  Examples:
    | existing state                           | order number | file name        |
    | not registered (INSERT path)             | <real value> | <real file name> |
    | registered by another path (UPDATE path) | <real value> | <real file name> |
```

(**Reference every Examples column from a step.** A column no step uses is decoration, and readers cannot tell the rows apart. Fill `<real value>` from real samples — if you can't, don't synthesize; ask for real data)

- **Derive Then from the spec's (source of truth's) list of update columns. Don't write it by looking at the implementation's SET columns** — an implementation bug would be copied into the acceptance criteria, and green would no longer prove correctness
- **One Examples row per path** (even if INSERT passes, run UPDATE separately. Keep a run that starts from a real file for each branch)
- **Write real file names and real values in Given** — if you can only write it by synthesizing an intermediate state, that is a sign the real data is missing (don't write "skipped because missing" as verified)
- **3–5 lines per Scenario. One Given, at most 3 chained Ands** (ten stacked lines are harder to read than bullets)
- **Map Scenario names to test names 1:1.** Without a runner (Cucumber/behave, etc.), Gherkin is just a format for humans, so if you can't map them, bullets are enough (a decorative feature file becomes a second spec)
- When putting it into a delegation seed, **add one line: "Scenarios are acceptance criteria, not the implementation format for tests"** (without it, the agent starts writing feature files with no framework)
- **Don't paste Gherkin into the PR body.** Just quote the Scenario name from the acceptance-criteria ✅/❌ rows (avoid managing it twice). If you feel like writing it out in the PR, that is a sign you implemented without acceptance criteria on the issue

### Leftovers: issue or PR stack layer

**The default is a layer; an issue is the exception.** Applying "task comes up → issue" unconditionally piles up issues even for continuations of the same story (real harm: leftovers that one PR would finish became a heap of issues, and agents reading them later treated them as open tasks).

30-second test: **Something you can't build once back on main = layer; something you can build from main = issue.**

| Aspect | Stack layer (`gh-stack` skill) | Issue |
|---|---|---|
| Dependency | Depends on the current branch's code (can't be built or reviewed from main alone) | Can be built independently from main |
| Timing | You do it in this work (before the stack is merged) | Deferred to another session or a later day |
| Story | Continuation to meet the same issue's acceptance criteria (backend → frontend → tests → docs) | A different goal or a different repo |
| Decision | Spec is settled; it just needs building | Needs the user's design decision or Arch Review |
| Nature | Needed because of the current change | A bug in existing code or a nearby improvement (the "report only" items in delegation acceptance criteria) |

- For a layer, follow `gh-stack`'s design guidance: one layer per unit where "a separate concern depends on what was just built". Name layers `<topic>/<concern>`.
- Anything that fits neither goes in the PR body's `## Out-of-scope notes`. **But don't leave it there**: before merging, write "layer / issue / won't do (reason)" for each item. For "won't do", recording it with the reason in the PR body is enough; don't create an issue.
- Sort leftovers reported by a delegated subagent with the same table. "Report only" is a rule that keeps subagents from fixing things on their own; it does not mean reported leftovers automatically become issues.

### Issue hierarchy and dependencies

**Work with 3 or more steps, or that takes 2 weeks or more, is split into "goal issue + child issues".** Use GitHub-native sub-issues (don't fake it with links in the body. The parent gets a progress bar, and agents can follow parent → children with `issue_read`).

| Level | What to write |
|---|---|
| **Goal issue (parent)** | Completion criteria, how far it has come, list of children (automatic). **Don't write work content** |
| **Child issue** | A step, bug, or improvement. One issue = one deliverable (PR, report, research note) |

- **At most 2 levels deep**. Wanting grandchildren is a sign the goal is cut too large
- Parent/child via `issue_write`'s `parent_issue_number` (at creation) or `sub_issue_write` (afterwards)
- **Sideways dependencies** (B can't start until A finishes) use GitHub issue dependencies (*blocked by*). MCP lacks them, so use GraphQL `addBlockedBy(input:{issueId, blockingIssueId})`; read with `issue { blockedBy blocking }`
- **Don't overdo it**: one-off tasks (a purchase, a submission, a single investigation) don't need a parent
- The weekly "this week's work" comes from **the child-issue list of open goal issues** (don't use the "next week" part of a progress report as a substitute for goals)
- When closing a child, also write `## Result` in the body as in "Recording rules when closing an issue". Close the parent only after all children are closed, rewriting "how far it has come" in the parent body as complete

### Architecture review gate (Arch Review)

What counts as a structural change, what is allowed before the GO, and the PR body's `Arch-Review:` line are defined in the `dev-flow` skill. Only the issue-side operations are here (follow the 3 lines below even where dev-flow is not installed).

- For an issue involving a structural change, set `Arch Review: Pending` when creating it, and write the chosen approach and design requirements in the body. While it is `Pending`, don't open an implementation PR. When delegating, state the gate status in the seed.
- It is lifted only after the user changes it to `Approved` (or gives an explicit GO). Even if the field is unset, a structural change needs a GO. When `Arch Review` is unavailable (repos without Issue Fields, personal accounts), get the GO in chat.
- Machine extraction: `list_issues(field_filters: [{field_name:"Arch Review", value:"Pending"}])`.

### Real-environment verification gate (Verification)

**An axis for tracking "the code is done, but it hasn't been checked because we can't touch the real environment".** It can't be derived from GitHub state (whether the PR is merged, whether the issue is open), so it lives in an Issue Field. Don't make fields for things that can be derived (they become duplicate records and go stale).

| Value | When to set it |
|---|---|
| `Pending` | Closing / merging while acceptance criteria **that can only be checked in the real environment** are still not done |
| `Verified` | Confirmed on the real environment (when the real-wiring issue is completed, update related issues to this value too) |
| `Not needed` (unset means the same) | No real-environment verification needed (docs, config, refactors) |

- **`Pending` does not block closing.** Write the unverified items in `## Result` as "not done (intentionally)", show where the leftovers go (a real-wiring issue, etc.), and you may close. The field remains after closing, so it can be tracked.
- Machine extraction: `list_issues(field_filters: [{field_name:"Verification", value:"Pending"}])` (**use state all to include closed ones**). This gives the list of "things we think work but nobody has checked".
- It shares a value name with `Arch Review: Pending` (the pre-implementation gate), but it is a different axis. **Arch Review is the gate before starting (may we start?); Verification is the gate after finishing (did we check on the real environment?).**

### Priority rules

User specified → that value / urgent, needs immediate action → Urgent / Start date is near or past → High / not specified → Medium.

### Status (project board lanes)

Todo / In Progress / Done are the Project's built-in Status field and **cannot be operated from MCP** (lanes are moved by hand). Only if automating, use GraphQL `updateProjectV2ItemFieldValue` (projectId is in the organization settings). Creating an Issue Field with the same name is no substitute.

### Recurring tasks: when to create issues and how they run

Recurrence is for classification and filtering, not an execution trigger. **Real tasks worth keeping a record of** → a scheduler auto-creates an issue each cycle (with Recurrence and a link to the previous issue) / **simple reminders and routine meetings** → no issue; handle them in reminders or routine jobs.

### Body vs. comments when updating an issue

**Write at the moment a decision is made. Don't batch it up at the end of the session.** If several turns pass without updating an issue you read, the workflow plugin's `issue-writeback` hook blocks Stop and prompts you to write back (up to 3 times per issue). If there really is no decision (only summarized it, only read it as an implementation spec), run the `dismiss` command given in the hook's message with a reason, then finish. After `/clear`, compaction, or resume, unreflected issues are notified again. For tracking across all sessions, run `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/issue-writeback.py" status --pending` (it matches against `claude agents --json` to show session names and whether they are alive; ended sessions with unreflected issues get a resume command).

**The body is "how things are now"; comments are "why it became so"**.

| Where | Content |
|---|---|
| **Body** | Current design, spec, remaining tasks, assumptions, completion criteria, primary-source evidence |
| **Comments** | History of changes, "why it was rewritten", explanation of the old design, interim findings |

- **When the design changes, rewrite the body** (don't add a correction comment and leave the body as is). Later agents read **only the body** with one `issue_read` call, so a stale body means work piles up on wrong assumptions.
- **Don't keep history in the body**. If the old design is explained in the body, someone skimming will mistake it for the current spec.
- **Put only "things that don't change until close" in the body.** Measured values, achievement rates, and "how far it has come" change on re-runs, so write how to get them (path, reproduction command) in the body and put the values, dated, in comments (e.g. an achievement rate can change not only its numerator but also its denominator on a re-run). Expected values, mapping tables, and real samples define what is correct and don't change, so they go inline in the body.
- Verify by machine: after rewriting, grep the body for keywords like `old design` or `why it was rewritten`.

### Recording rules when closing an issue (all issues)

Even after closing, issues are referenced from other issues and other agents (agents read the body with one `issue_read` call and miss scattered comments). **Put the conclusion in the body, not in comments**:

| Target | What to do before closing |
|------|------------------|
| Every issue (completed) | `## Result` at the end of the body (1–5 lines: conclusion / done and not done / related PR) |
| Recurring tasks with Recurrence set | The detailed **`## Notes for next time`**: date done / how and where it was submitted / screens and tools used / whether attachments were needed and why / lead time / stumbling points / improvement notes |
| duplicate / not_planned | No body addition needed (`state_reason` and a one-line comment) |

- Older issues may use `## 結果` and `## 次回への引き継ぎ`; both are still accepted.
- The test is "who will open this issue next, and what will they want to know". Comments are optional, as a log of interim progress.
- When an automation agent closes on someone's behalf and the record is thin, ask the user one question before closing (don't close without a record).
- The next issue of a recurring task links to the previous one and copies `## Notes for next time` as a starting draft.

### Linking PRs and issues (`Closes` / `Refs`)

**Every PR body must contain either `Closes <owner/repo#N>` or `Refs <owner/repo#N>`.** A PR with neither can't be traced to its issue after merging. **Closing keywords also work for issues in other repos** (GitHub Docs "Linking a pull request to an issue": https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue ). `Refs` only creates a cross-reference and does not close.

| What to write | Condition |
|---|---|
| **`Closes`** | The issue's **acceptance criteria are all expected to be ✅**. **Finish writing `## Result` in the issue body before merging** |
| **`Refs`** | Either of the above is missing. **Write "unmet items" and "where the leftovers go (layer / issue number / won't do)" in the PR body** |

- **`## Result` is a precondition for merging a `Closes` PR**. Auto-close leaves no record in the body, so writing it after the merge means a close without a record (writing `Closes` when opening the PR is fine). The `dev-flow-gate` hook in the same plugin blocks merges where it isn't written.
- **Post-merge cleanup of an issue referenced with `Refs` is the responsibility of the delegating (main) session.** Don't close it while unmet acceptance criteria remain; close it after the leftovers are done, moved to another issue, or decided against. The delegate's (subagent's or other session's) scope is "up to opening the PR", and post-merge cleanup is not the delegate's job. If nobody owns this, "PR merged, issue open" stays until someone happens to notice.
- Catch it by machine: compare `search_pull_requests` (`is:merged <issue number>`) with the issue state. A scheduled morning check, if you have one, is the safety net, but **the rule exists to move "someone notices later" forward to "decided when the PR is opened"**.

### Date field rules

**Clear deadline** (year-end tax adjustment, tax filing, contract renewal, etc.) → proactively propose a schedule from the usual deadline (e.g. "Shall I set Start date: 11/1 and Target date: 11/30?"). **Unclear deadline** → ask the user.

### Notes

The only thing MCP can't cover is moving Status lanes on the project board (use GraphQL only when needed). Priority and dates are fully handled by Issue Fields (MCP).
