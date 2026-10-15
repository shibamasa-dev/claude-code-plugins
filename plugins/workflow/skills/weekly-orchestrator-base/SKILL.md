---
name: weekly-orchestrator-base
description: Base practices (the project-independent part only) for an orchestrator: one long-lived session per repository (title starting with 🎯) that runs a cycle (a week by default) as plan → bundle into batches and delegate → verify → close out, keeping its state in the cycle issue's plan section so a manual /clear loses nothing. Project orchestrator skills build on it by saying "read and follow weekly-orchestrator-base" at the start; when you see that, always read this first. Also use it on its own to set up a repo's orchestrator session, route a batch to a subagent or a child session, resume after a /clear, receive a batch report or a report from another session, or close a cycle, or in Japanese 「オーケストレータを作って」「オーケストレータセッション」「このリポのオーケストレータ」「オーケストレータの基本所作」「オーケストレータとして計画と委譲だけして」「このバッチは subagent に出す？別セッションに出す？」「委譲先を subagent にするか別セッションにするか」「/clear していい？」「サイクルを締めて次の issue に計画を書いて」「バッチの報告が来たので受け取って」. Holds no shared resources or report building (the project skill adds those).
---

# weekly-orchestrator-base — base practices for an orchestrator

**Split with the project skill**: this skill holds only the practices that are the same in every project.
The cycle boundary (weekday, submission), the shared-resource table, scripts that gather status, how to build reports,
and issue titles and auto-creation belong to the project skill. The project makes these practices concrete and adds to them,
and for the concrete parts (per-resource locks, extra fields, and so on) follow the project. If the project skill contains
something that contradicts a base practice (routing delegation, the don'ts), do not silently pick one; ask the user.
A repository without a project skill uses "Defaults when the repository has no project skill" below.

## Role

The orchestrator **only plans, delegates, and verifies. It does not implement.**
If it also takes on implementation, its context will not last a week, and it loses its memory of the plan and progress along with it.

## Source of truth for state

**The source of truth is the "plan section" in the cycle issue body** (from `<!-- weekly-orchestrator:plan -->` to `<!-- /weekly-orchestrator:plan -->`, each at the start of a line).
The template, the marker contract, and the splice contract are in `references/plan-section.md`.

- Do not create state that exists only in the conversation. After a `/clear`, the orchestrator resumes by reading only this section
- **Rewrite it the moment you decide, the moment you delegate, and the moment you receive a result.** If you batch the writes for later, a `/clear` in between loses them
- The body says "where things stand now"; the history goes in comments
- **Every write to an issue (creating, updating the body, closing, commenting) follows the `issue-ops` skill.** This skill does not decide the means of writing (MCP or gh). When a plan or answer lists a write, do not write only the command; state "following issue-ops" explicitly (so the reader can check the means in issue-ops)

## The orchestrator session

How the orchestrator itself is kept. This is the same in every project.

- **One orchestrator session per repository** (per working directory; worktrees of the same repository count as that repository). The user pins it in the sidebar and keeps using it every day, instead of starting a new one-off session for each piece of work
- **Its title starts with `🎯 <repo name>`** (e.g. `🎯 my-repo`). Set it once, when the orchestrator is created (rename the session in the app, or with `set_session_title` where that tool is available); never change titles automatically afterwards. Exactly one live session per repository carries this marker: the `orchestrator-report` hook uses it to find the orchestrator, and does nothing when it finds none or several
- **Context**: the user runs `/clear` on this same session whenever they like; no other session takes over. Because a clear can come at any moment, write every decision, delegation and received result to the plan section the moment it happens (see "Source of truth for state"); after a clear, resume by reading the plan section (step 6)
- **Delegation split**: work that will produce a PR goes to a child session (Claude desktop: `start_session`, which makes it a linked session whose turn-end notes reach the orchestrator); read-only investigation or verification goes to a subagent. Details in step 3
- **Reports from sessions the orchestrator did not start**: the `orchestrator-report` hook tells other sessions that write to the same repository to send the orchestrator a one-line report by SendMessage when they create or update a PR or write to an issue. Treat such a message as a report: verify it (`gh pr view`, `gh issue view`), then update the plan section. Work that was not in the plan goes into the batch table as unplanned (step 4)
- **Turns started by another session's message cannot start sessions.** In a turn that began with a child's turn-end note or another session's report, the app refuses to start new sessions (verified). In such a turn, update the plan section and, if the next batch is due, propose it (a proposal card, or ask the user) instead of starting it. Starting batches needs the user's own message anyway
- **Claude Projects (cloud)**: when `CLAUDE_CODE_PROJECTS_SESSION=1`, the Projects coordinator conversation is the orchestrator; do not create a `🎯` session for that work. Cloud sessions cannot send messages to local sessions, so they do not report; accept that and collect their results from the PRs and issues
- **Known gap**: the hook finds the orchestrator with `claude agents --json`, which lists only sessions whose process is running. While the orchestrator's process is not running (e.g. after the app restarts, before the session is opened again), no session is told to report; catch up from PRs and issues when you resume

## Defaults when the repository has no project skill

When the repository has its own orchestrator skill, its values override these.

- **Cycle**: one week (Monday to Sunday)
- **Cycle issue title**: `Orchestrator: <repo> <YYYY>-W<ww>` (ISO week, e.g. `Orchestrator: my-repo 2026-W42`). Create it following `issue-ops` if none exists for the current week
- **Gathering the situation**: the plan section of the cycle issue plus the reports received (batch reports and reports from other sessions). Nothing else is collected automatically
- **Close-out boundary**: `**Cutoff**:` at the end of the cycle

## Steps

### 1. Make the plan

How to gather the situation (which issues, PRs, and records of the previous cycle to look at) follows the project skill (without one, the defaults above). From what you gathered, decide in this order.

1. **Choose the targets**: from the goal issues and their child issues, choose what to advance this cycle
   - Exclude issues waiting for a design review (when the project marks them with an issue field or label, e.g. `Arch Review: Pending`) and goals whose start condition ("start after ... progresses", etc.) is not met yet. Write them under "deferred" in the plan section **with the reason** (if you drop them silently, neither you after a `/clear` nor the user can trace why)
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

| Delegate to | Choose when |
|---|---|
| **subagent** (`Agent` tool, background) | Read-only investigation or verification (no PR comes out of it), and all of these hold: no dialogue or approval with the user is needed / it does not touch computer use or remote physical machines (anything involving permission dialogs or screen locks) / it is expected to finish within a few hours |
| **Child session** (a separate session) | The work will produce a PR, or any condition for a subagent does not hold (it needs questions to or approval from the user / it touches a physical machine / it is long work that would outlive the next `/clear`) |

For child sessions, use the first route available, in this order: ① `start_session` (`initiation: "user_asked"` for batches in the plan the user confirmed; `own_initiative` for ones you add on your own judgment, which wait as a card until the user starts them) ② a skill or mechanism that can start another session in a waiting state without starting work right away (if the environment has one; do not configure it to run unattended) ③ a prompt for pasting plus `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" write` to leave the entry point.

- Write each prompt from the skeleton in `references/task-prompt.md`, **in full for every batch** (the receiver knows neither the history nor the other batches' prompts)
- Before sending, fill in "Run via" and "Status" (`Running`) in the plan section's batch table; then send. If sending fails, set Status back to `Not started`, or to `Blocked (reason)` if it can't be retried now
- A subagent's final report arrives in its completion notification. A child session's interim and final reports arrive by SendMessage (write the recipient = the orchestrator's session name, `🎯 …`, into the prompt). A session started with `start_session` is a linked session: it also notifies you each time it ends a turn, but with only the first 400 characters of its latest report, so still have the full reports sent by SendMessage

### 4. Receive the results

- **Verify the report's claims yourself before updating the status**: `gh pr diff`, running the tests, reading the files directly. Do not turn "all tests pass" or "done" in a report straight into `Done`
- Keep `PR #N` (a PR exists but is not merged) separate from `Done` (merged and meeting the acceptance criteria). Merging is the user's decision; the orchestrator does not merge either
- A report from a session you did not start (sent because of the `orchestrator-report` hook) is handled the same way: verify, then record it. If it is not in the batch table, add a row with Batch `Unplanned: <what>`, Run via `reported by <session name>`, and the verified Status
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
3. After closing out, the context is heavy, so suggest a `/clear` (step 6) before starting the next plan

### 6. Clearing the context

No other session takes over. The user clears this same session with `/clear` whenever they like, and the orchestrator carries on from the plan section.

1. **Keep the plan section current so a clear loses nothing.** Decisions, delegations and received results are already written as they happen; before a natural break, also fill in "Resume point" (what to do next, the batches being waited on and the session each one reports from)
2. **Suggest a clear** when any of these holds: a compaction happened / you have read 3 or more batch reports / right after closing out. Suggest it once; the user decides when
3. **If subagents are running, say so before the user clears.** A subagent's report comes back only into this conversation, so clearing while one runs can lose its report. Name them and suggest waiting for their reports first
4. **After a clear**: find the cycle issue (the project skill's title, or the default title), read its plan section, check running child sessions with `ListAgents`, and resume from "Resume point". Child sessions keep reporting to the same session name, so nothing needs re-routing

## Don'ts

- Delegating without writing it in the plan section (after a `/clear`, nobody knows that batch is running)
- Letting an issue that is waiting for a design review be executed
- Starting a batch without the user's OK by a method that runs without confirmation (such as a separate session with bypassPermissions)
- Chopping work into one batch per item / sending out 3 or more at once
- Rewriting anything outside the plan section (the outside belongs to the project or to auto-creation)
- Closing the cycle issue before closing out / appending post-cutoff work to the closed issue
- Letting the user clear while a subagent is running without telling them
- Changing session titles automatically, or keeping a second `🎯` session for the same repository
- Starting a session in a turn started by another session's message (the app refuses; propose it instead)
- Setting the status to `Done` without verifying the report

## What the project skill adds

These override "Defaults when the repository has no project skill".

- The cycle boundary (weekday, submission), and whether the first line of `## Result` uses `**Cutoff**:` or `**Submitted**:`
- The means of gathering the situation (scripts, issues to look at), the cycle issue title, and whether it is auto-created
- Headings and fields added to the plan section (milestones, the plan for the previous report, etc.)
- The shared-resource table and per-resource locks
- Project-specific lines for "Read first" and "Rules" in delegation prompts
- Reporting tasks done within the cycle, such as reports
