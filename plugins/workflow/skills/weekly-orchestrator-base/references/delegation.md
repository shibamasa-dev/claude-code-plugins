# Choosing where to delegate, and receiving reports and winding down

## 1. Subagent or separate session

| Question | Yes → | No → |
|---|---|---|
| Does it need questions to or approval from the user? | Separate session | Next |
| Does it touch computer use or remote physical machines (anything involving permission dialogs or screen locks)? | Separate session | Next |
| Is it expected to finish within a few hours / can it avoid running across a handover? | **subagent** | Separate session |

Why:

- A subagent cannot talk with the user. If it ends up waiting for an answer or approval, it stalls and no report comes back
- Permission dialogs and screen locks on physical machines assume a person looking at the screen and operating it. A subagent that cannot talk gets stuck
- **A subagent stops together with its parent session.** If you give long work to a subagent, the work stops as soon as the orchestrator hands over
- Conversely, short work with no dialogue is lighter as a subagent (no chip to click or session to attach, and the report comes back automatically in the completion notification)

When in doubt, use a separate session (the cost of stalling is bigger).

## 2. How to send out

### subagent

- With the `Agent` tool, `run_in_background: true` (the default), `isolation: "worktree"` (separate working tree, so the orchestrator's working tree stays clean)
- Give it a `name` so you can ask about its status with SendMessage while it runs
- The final report **appears as-is in the body of the completion notification**. Fix its shape with the prompt's "Final report format"
- "Run via" column in the plan section: `subagent <name>`

### Separate session (the first one available, in this order)

| Order | Route | How to use |
|---|---|---|
| 1 | `spawn_task` (Claude desktop; find it with `ToolSearch`) | It only shows a chip; work starts when the user clicks it. Write the `task_id` in the plan section |
| 2 | A skill or mechanism that can start another session in a waiting state (if the environment has one) | Use a separate working tree and start it in a waiting state (it does not move until the user enters that session and says "start"). **Do not configure it to run unattended** (if the mechanism starts work unattended when given an entry issue, do not use that option). Write the entry issue in the prompt body. Write the started session's identifier in the plan section |
| 3 | Neither is available (CLI alone, cloud, etc.) | Output the prompt for pasting and leave the entry point with `handoff write --entry <owner>/<repo>#<cycle issue>`. In the plan section, write `paste-in` |

- Have interim and final reports sent by SendMessage to the recipient written in the prompt (the orchestrator's session name). Unless you have them sent, all the orchestrator receives is a "session ended" notification
- The session name is the `<name>` in the first line of `ListAgents` (`This session is <name> [ref]`). Do not include `[ref]`

## 3. Receiving

- For each claim in a report, run the reproduction command yourself: `gh pr diff <N>` / running the tests / reading the files directly. Do not treat claims without one (those marked "guess") as fact until verified
- Rewrite the status in the plan section only after verifying. If there is a PR that is not merged, `PR #N`; if merged and the acceptance criteria are verified, `Done`
- If you want to know progress, do not make the user go and look. Check idle/busy with `ListAgents` and ask the agent itself by SendMessage
- `idle` is a notice of being free, not a notice of completion. Until a report arrives, treat it as still running, and do not make decisions from reading its intermediate output
- **The orchestrator owns review-waiting for PRs made by subagents.** A subagent ends as soon as it completes, so once you receive a PR (after verifying), start `pr-review-triage` yourself. For a separate-session batch, that session waits for reviews following the repo's rules

## 4. Winding down

Leaving separate sessions around after they are done increases parallelism and breaks Remote Control.

- **OK to wind down**: the PR is merged (`prState: MERGED` in `list_sessions`) and `isRunning: false`
  - Claude desktop sessions: `archive_session` (the PR and branch remain)
  - Other routes: wind down with the shutdown method of whatever mechanism started it
- **Do not wind down**: sessions whose PR is OPEN / sessions still working (`isRunning: true`, no PR yet). Archiving also cleans up that session's worktree, so winding down before merging erases unmerged work
- A subagent ends by itself when it completes, so there is nothing to wind down. While one is running, do not end the orchestrator (do not hand over)
