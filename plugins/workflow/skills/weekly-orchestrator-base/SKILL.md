---
name: weekly-orchestrator-base
description: Base practices (the project-independent part only) for an orchestrator that runs a cycle (a week) as plan → bundle into batches and delegate → verify → close out and move on. Project weekly orchestrator skills build on it by saying "read and follow weekly-orchestrator-base" at the start; when you see that, always read this first. Also use it on its own for routing a batch to a subagent or a separate session, handing over to a successor, closing a cycle, or receiving a batch report, or in Japanese 「オーケストレータの基本所作」「オーケストレータとして計画と委譲だけして」「このバッチは subagent に出す？別セッションに出す？」「委譲先を subagent にするか別セッションにするか」「代替わりして」「後継に渡して」「コンテキストが重いので引き継いで」「サイクルを締めて次の issue に計画を書いて」「バッチの報告が来たので受け取って」. Holds no repos, shared resources, cycle weekdays, or report building (the project skill adds those).
---

# weekly-orchestrator-base — base practices for an orchestrator

**Split with the project skill**: this skill holds only the practices that are the same in every project.
The cycle boundary (weekday, submission), the shared-resource table, scripts that gather status, how to build reports,
and issue titles and auto-creation belong to the project skill. The project makes these practices concrete and adds to them,
and for the concrete parts (per-resource locks, extra fields, and so on) follow the project. If the project skill contains
something that contradicts a base practice (routing delegation, the order of a handover, the don'ts), do not silently pick one; ask the user.

## Role

The orchestrator **only plans, delegates, and verifies. It does not implement.**
If it also takes on implementation, its context will not last a week, and it loses its memory of the plan and progress along with it.

## Source of truth for state

**The source of truth is the "plan section" in the cycle issue body** (from `<!-- weekly-orchestrator:plan -->` to `<!-- /weekly-orchestrator:plan -->`, each at the start of a line).
The template, the marker contract, and the splice contract are in `references/plan-section.md`.

- Do not create state that exists only in the conversation. A successor orchestrator resumes by reading only this section
- **Rewrite it the moment you decide, the moment you delegate, and the moment you receive a result.** If you batch the writes for later, a handover in between loses them
- The body says "where things stand now"; the history goes in comments
- **Every write to an issue (creating, updating the body, closing, commenting) follows the `issue-ops` skill.** This skill does not decide the means of writing (MCP or gh). When a plan or answer lists a write, do not write only the command; state "following issue-ops" explicitly (so the reader can check the means in issue-ops)

## Steps

### 1. Make the plan

How to gather the situation (which issues, PRs, and records of the previous cycle to look at) follows the project skill. From what you gathered, decide in this order.

1. **Choose the targets**: from the goal issues and their child issues, choose what to advance this cycle
   - Exclude issues with `Arch Review: Pending` and goals with a start condition ("start after ... progresses", etc.). Write them under "deferred" in the plan section **with the reason** (if you drop them silently, the successor and the user cannot trace why)
2. **Set the minimum bar**: what must be finished by the end of the cycle
   - The minimum bar is **a floor, not a ceiling**. Once it is done, send out the next batch toward the goal
   - Do not silently carry over what does not fit in the weekdays. Consult the user on what to push to the next cycle
   - **Do not fill unknown premises (milestone scope, what is needed and how far, how to read a deadline) with guesses; ask the user**
3. **Adjust the sub-steps**: if an item on the minimum bar has no child issue, create one. Split, merge, or close child issues whose granularity does not fit. Record each adjustment as one line under "Sub-step adjustments" in the plan section
4. **Bundle into batches** (step 2)
5. **Show the whole plan to the user at once and get an OK.** Only after the OK, write it into the plan section and start the batches.
   This OK also counts as the instruction to start the batches listed in the plan. To add a batch that is not in the plan, get an OK each time

### 2. Bundle into batches

The detailed rules and the locks for running in parallel are in `references/batching.md`. The gist:

- Put items in the same batch if **any one** of these holds: they touch the same files / they use the same shared resource / one depends on the other / each is small
- **Send out at most 1–2 batches at a time.** Look at the results of the previous batch before sending the next
- When running in parallel, write both the `mkdir` lock (the turn-taking rule) and the ownership ranges within shared files into both prompts
- The shared-resource table belongs to the project skill

### 3. Choose where to delegate and send it out

Details (how to call each route, how to receive reports, how to wind down) are in `references/delegation.md`.

| Delegate to | Choose when (all must hold) |
|---|---|
| **subagent** (`Agent` tool, background, `isolation: "worktree"`) | No dialogue or approval with the user is needed / it does not touch computer use or remote physical machines (anything involving permission dialogs or screen locks) / it is expected to finish within a few hours |
| **Separate session** | Any of the above does not hold = it needs questions to or approval from the user / it touches a physical machine / it is long work that runs across a handover |

For separate sessions, use the first route available, in this order: ① `spawn_task` ② a skill or mechanism that can start another session in a waiting state without starting work right away (if the environment has one; do not configure it to run unattended) ③ a prompt for pasting plus `handoff write` to leave the entry point.

- Write each prompt from the skeleton in `references/task-prompt.md`, **in full for every batch** (the receiver knows neither the history nor the other batches' prompts)
- Before sending, fill in "Run via" and "Status" (`Running`) in the plan section's batch table; then send
- A subagent's final report arrives in its completion notification. A separate session's interim and final reports arrive by SendMessage (write the recipient = the orchestrator's session name into the prompt)

### 4. Receive the results

- **Verify the report's claims yourself before updating the status**: `gh pr diff`, running the tests, reading the files directly. Do not turn "all tests pass" or "done" in a report straight into `Done`
- Keep `PR #N` (a PR exists but is not merged) separate from `Done` (merged and meeting the acceptance criteria). Merging is the user's decision; the orchestrator does not merge either
- Do not make the user go and check progress; ask yourself (look at names and idle/busy with `ListAgents`, then ask by SendMessage)
- For an issue that a PR referenced with Refs (not Closes), check what is left, decide whether to close or keep it, and handle it following `issue-ops`
- Wind down separate sessions that are no longer needed: **only merged ones (`prState: MERGED` and `isRunning: false`)**. Wind them down with `archive_session` / the shutdown method of whatever mechanism started them. **Do not wind down sessions whose PR is OPEN or that are still working** (archiving also cleans up the worktree, which would erase unmerged work)
- When one batch is cleared, send out the next batch that depended on it

### 5. Close out and move to the next cycle

The project decides the boundary (weekday, submission) and whether to use "cutoff" or "submission".

1. Close the cycle issue with the `issue-ops` close procedure. **When closing, write `## Result` at the end of the body** (older cycle issues may have `## 結果`; see `references/plan-section.md`):
   - The first line is the boundary time: `- **Cutoff**: YYYY-MM-DD HH:MM` (or `- **Submitted**: …`). The close time does not substitute for it (if there is a gap, the work in between falls into neither cycle)
   - Then the status of the minimum bar and where the pushed items went (carried over to the next cycle / returned to an issue / dropped)
   - When the next cycle starts counting from something other than the boundary, add `- **Tally start**: YYYY-MM-DD HH:MM`
2. The next cycle's issue: **if one with the same title already exists (auto-created, etc.), do not create another.** Replace **only the plan section (between the markers)** of that issue (writing following `issue-ops`), and keep everything outside it (auto-creation notes, etc.). If the plan section is already filled in before you replace it (plan status is `Confirmed`), do not rewrite it; ask the user. If there is no such issue, create one following `issue-ops`
3. After closing out, the context is heavy, so it is best to hand over in step 6 before starting the next plan

### 6. Handover

Hand over when any of these holds: a compaction happened / you have read 3 or more batch reports / right after closing out. This cannot be detected mechanically, so judge by these signs.

1. **Do not hand over while a subagent is running.** Ending the parent session also stops the subagent. Wait for it to finish first, receive its report, then proceed
2. **Write the state first.** In the plan section's "Handover", write the generation, what to do next, and the batches being waited on (and who they report to). Do not send out the successor before writing
3. Send out the successor via the **separate-session route** from step 3 (the successor runs long and talks with the user, so it is never a subagent). Use the "For a successor orchestrator" prompt in `references/task-prompt.md`
4. Tell each running separate-session batch by SendMessage that its report recipient has changed to the successor's session name. For any you could not tell, write "report recipient is still the old generation" in "Handover" (the successor will go and ask)
5. Once the successor is out, do not send out new batches yourself. Rewrite the "Orchestrator" line in the plan section to the next generation and finish

## Don'ts

- Delegating without writing it in the plan section (a batch runs that the successor does not know about)
- Letting an issue with `Arch Review: Pending` be executed
- Starting a batch without the user's OK by a method that runs without confirmation (such as a separate session with bypassPermissions)
- Chopping work into one batch per item / sending out 3 or more at once
- Rewriting anything outside the plan section (the outside belongs to the project or to auto-creation)
- Closing the cycle issue before closing out / appending post-cutoff work to the closed issue
- Handing over while a subagent is running
- Setting the status to `Done` without verifying the report

## What the project skill adds

- The cycle boundary (weekday, submission), and whether the first line of `## Result` uses `**Cutoff**:` or `**Submitted**:`
- The means of gathering the situation (scripts, issues to look at), the cycle issue title, and whether it is auto-created
- Headings and fields added to the plan section (milestones, the plan for the previous report, etc.)
- The shared-resource table and per-resource locks
- Project-specific lines for "Read first" and "Rules" in delegation prompts
- Reporting tasks done within the cycle, such as reports
