# The plan section (placed in the cycle issue body)

The orchestrator's **source of truth** for state. A successor orchestrator reads only this and resumes from where it left off.
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

### Handover
- Orchestrator: generation 1 (after sending out a successor, write the generation and how it was started)
- Next: 
- Waiting on batches: (batch number, session name the report goes to)
<!-- /weekly-orchestrator:plan -->
```

### How to fill the fields

- **Plan status**: `Draft` while it is still the template. Once you get the user's OK and write it in, `Confirmed YYYY-MM-DD`. The successor uses this to decide whether to "make the plan" or "resume from where it left off"
- **Minimum bar**: write as checkboxes. Items still `- [ ]` at close-out become candidates for carry-over
- **Run via column**: `subagent <name>` / `start_session <name>` (the name it returns; `start_session <task_id>` for a card not started yet) / `<route> <identifier>` (other separate sessions) / `paste-in`
- **Status column**: `Not started` / `Running` / `PR #N` (a PR exists but is not merged) / `Done` (merged and acceptance criteria verified) / `Blocked (reason)`
- **Handover**: always write it before a handover. If you could not tell a running separate-session batch about the change of report recipient, write "report recipient is still the old generation"
- Older cycle issues may use the Japanese template; read `未確定` / `確定` as `Draft` / `Confirmed`, and the statuses `未着手` / `実行中` / `完了` / `止まっている` as `Not started` / `Running` / `Done` / `Blocked`

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
