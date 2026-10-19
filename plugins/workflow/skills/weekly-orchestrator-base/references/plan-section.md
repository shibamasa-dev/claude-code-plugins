# The plan section (placed in the cycle issue body)

The orchestrator's **source of truth** for state. After a `/clear`, the orchestrator reads only this and resumes from where it left off.
Rewrite it the moment you decide, the moment you delegate, and the moment you receive a result. History goes in comments.
Every write follows the `issue-ops` skill.

## Marker contract

- Start `<!-- weekly-orchestrator:plan -->`, end `<!-- /weekly-orchestrator:plan -->`
- Put each **at the start of a line, alone on that line**. A marker written inside explanatory text (mid-line, inline code) does not count as a section boundary
- Only one plan section per body
- Project scripts may search for the section by these strings. Do not change them

## Splice contract

When rewriting the plan section (confirming the plan, updating status, writing into the next cycle's issue),
**replace only what is between the markers and do not change a single character outside.** The outside (auto-creation notes,
report checklists, etc.) belongs to the project or the workflow, not to the orchestrator.

When putting the next cycle's plan into an existing issue (auto-created, etc.):

1. Check whether an issue with the same title exists. If it does, do not create a new one (no duplicates)
2. Read that issue's body and find the plan section
   - No section → do not write; ask the user (where to put it is the project's call)
   - The section is already filled in (plan status is `Confirmed …`) → someone has already written the plan. Do not rewrite it; ask the user
3. Build a body where only the part between the markers is replaced with the new content, and write it following `issue-ops`

Replacing the whole body with the template erases the notes outside. That is why you "replace only the plan section".

## Template (the base shape)

Projects may add headings and fields (milestones, the plan for the previous report, etc.). Do not remove the base headings.
Fill in `{period}` to match the project's cycle.

```markdown
<!-- weekly-orchestrator:plan -->
## Plan for this cycle ({period})

**Plan status**: Draft (before the user's OK)

### Goal progress
| Goal | Children done | Current work | Next move / blocked reason |
|---|---|---|---|

### Target goals
| Goal | Child issues to advance this cycle | Deferred child issues (reason) |
|---|---|---|

### Minimum bar (must finish by the end of the cycle; a floor, not a ceiling)
- [ ] 

### Batches (units of execution)
| # | Batch | Entry issue | Shared resources | Order | Run via | Status |
|---|---|---|---|---|---|---|

### Sub-step adjustments
- (one line per child issue created, merged, or closed, with the reason; "none" if there are none)

### Resume point
- Next: 
- Waiting on batches: (batch number, session name the report comes from)
<!-- /weekly-orchestrator:plan -->
```

### How to fill the fields

- **Goal progress**: **every open goal, one row each**, whether or not it was chosen this cycle. Rebuild it from the goal list each cycle (do not carry the previous cycle's rows over); a goal that is blocked or has not moved still gets a row. Children done is `completed/total` of its child issues; Current work names the batch or child issue in progress (empty if none); the last column holds the next child to advance, or why the goal is blocked (waiting for a design review, a start condition, the user). A line of work the project tracks outside issues (a progress table, a database) may get a row too, with its own count. Projects may add columns (e.g. how many children wait for a design review, when a child was last updated)
- **Target goals**: the subset of Goal progress chosen for this cycle, with the child issues to advance. Its "Deferred child issues" column is per child within a chosen goal; Goal progress's last column is per goal across all of them. Goal progress answers "how far along is each goal"; Target goals and Batches answer "what this cycle does about it"
- **Plan status**: `Draft` while it is still the template. Once you get the user's OK and write it in, `Confirmed YYYY-MM-DD`. After a `/clear`, the orchestrator uses this to decide whether to "make the plan" or "resume from where it left off"
- **Minimum bar**: write as checkboxes. Items still `- [ ]` at close-out become candidates for carry-over
- **Run via column**: `subagent <name>` / `start_session <name>` (the name it returns; `start_session <task_id>` for a card not started yet) / `<route> <identifier>` (other separate sessions) / `paste-in`
- **Status column**: `Not started` / `Running` / `PR #N` (a PR exists but is not merged) / `Done` (merged and acceptance criteria verified) / `Blocked (reason)`
- **Batch column**: work that was not in the plan but was reported by another session goes in as `Unplanned: <what>`, with Run via `reported by <session name>`
- **Resume point**: keep it current before any natural break, so the orchestrator can carry on after a `/clear`. It is the cycle's to-do list, not a progress report: goals that were not chosen or are blocked do not appear in it
- Older cycle issues may use the Japanese template; read `未確定` / `確定` as `Draft` / `Confirmed`, and the statuses `未着手` / `実行中` / `完了` / `止まっている` as `Not started` / `Running` / `Done` / `Blocked`. A project template may name the Goal progress heading 「ゴール別の進み具合」

## `## Result` when closing

Append it outside the plan section, at the end of the body (the `issue-ops` close procedure).

```markdown
## Result
- **Cutoff**: YYYY-MM-DD HH:MM        ← the boundary time. The project decides whether to use `**Submitted**:` instead
- **Tally start**: YYYY-MM-DD HH:MM   ← only when the next cycle starts counting from something other than the boundary
- Minimum bar: met N / M (not met: …)
- Pushed items: #… → carried over to the next cycle / #… → returned to an issue / #… → dropped (reason)
```

The boundary time becomes the starting point of the next cycle. The close time does not substitute for it.
Older cycle issues and project skills may use the Japanese `## 結果` with `**締め**:` / `**提出**:` / `**集計起点**:`; treat them as `## Result` with `**Cutoff**:` / `**Submitted**:` / `**Tally start**:`.
