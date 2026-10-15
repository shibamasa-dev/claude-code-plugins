# Choosing where to delegate, and receiving reports and winding down

## 1. Subagent or child session

| Question | Yes → | No → |
|---|---|---|
| Will it produce a PR (anything beyond read-only investigation or verification)? | Child session | Next |
| Does it need questions to or approval from the user? | Child session | Next |
| Does it touch computer use or remote physical machines (anything involving permission dialogs or screen locks)? | Child session | Next |
| Is it expected to finish within a few hours, before the user is likely to `/clear` the orchestrator? | **subagent** | Child session |

Why:

- A subagent cannot talk with the user. If it ends up waiting for an answer or approval, it stalls and no report comes back
- Permission dialogs and screen locks on physical machines assume a person looking at the screen and operating it. A subagent that cannot talk gets stuck
- **A subagent's report comes back only into the orchestrator's conversation.** If you give long work to a subagent, a `/clear` in between can lose its report
- Work that produces a PR goes to a child session: the PR then has an owner that waits for its reviews and answers them, and with `start_session` the orchestrator still hears each turn end
- Conversely, short read-only work with no dialogue is lighter as a subagent (no card to start or session to attach, and the report comes back automatically in the completion notification)

When in doubt, use a child session (the cost of stalling is bigger).

## 2. How to send out

### subagent

- With the `Agent` tool, `run_in_background: true` (the default). Add `isolation: "worktree"` when it runs builds or tests that write to the working tree, so the orchestrator's working tree stays clean
- Give it a `name` so you can ask about its status with SendMessage while it runs
- The final report **appears as-is in the body of the completion notification**. Fix its shape with the prompt's "Final report format"
- "Run via" column in the plan section: `subagent <name>`

### Child session (the first route available, in this order)

| Order | Route | How to use |
|---|---|---|
| 1 | `start_session` (Claude desktop) | It becomes a linked session of the orchestrator. `initiation: "user_asked"` for a batch in the plan the user confirmed (it starts immediately); `own_initiative` for a batch you add on your own judgment (it only shows a card; nothing runs until the user starts it). Pass the full prompt as `prompt`; with `context: "fresh"` (the default) also pass `background`. Write the returned session `name` in the plan section (for an `own_initiative` card the user hasn't started yet, its `task_id`) |
| 2 | A skill or mechanism that can start another session in a waiting state (if the environment has one) | Use a separate working tree and start it in a waiting state (it does not move until the user enters that session and says "start"). **Do not configure it to run unattended** (if the mechanism starts work unattended when given an entry issue, do not use that option). Write the entry issue in the prompt body. Write the started session's identifier in the plan section |
| 3 | Neither is available (CLI alone, cloud, etc.) | Output the prompt for pasting and leave the entry point with `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" write --entry <owner>/<repo>#<cycle issue>`. In the plan section, write `paste-in` |

- Have interim and final reports sent by SendMessage to the recipient written in the prompt (the orchestrator's session name). A session started with `start_session` notifies the orchestrator each time it ends a turn, but with only the first 400 characters of its latest report; other routes send only a "session ended" notification
- The session name is the `<name>` in the first line of `ListAgents` (`This session is <name> [ref]`). Do not include `[ref]`

## 3. Receiving

- For each claim in a report, run the reproduction command yourself: `gh pr diff <N>` / running the tests / reading the files directly. Do not treat claims without one (those marked "guess") as fact until verified
- Rewrite the status in the plan section only after verifying. If there is a PR that is not merged, `PR #N`; if merged and the acceptance criteria are verified, `Done`
- If you want to know progress, do not make the user go and look. Check idle/busy with `ListAgents` and ask the agent itself by SendMessage
- `idle` is a notice of being free, not a notice of completion. Until a report arrives, treat it as still running, and do not make decisions from reading its intermediate output
- A child session that creates a PR waits for its reviews itself, following the repo's rules. Subagents do not create PRs under this split; if one did anyway, the orchestrator owns waiting for that PR's reviews (start `pr-review-triage` after verifying)
- Reports from sessions you did not start (sent because of the `orchestrator-report` hook) are received the same way: verify, then record them in the plan section, as an `Unplanned: …` row if they are not in the batch table

## 4. Winding down

Leaving child sessions around after they are done keeps idle sessions running, which wastes resources and can make connections to them unstable.

- **OK to wind down**: the PR is merged (`prState: MERGED` in `list_sessions`) and `isRunning: false`
  - Claude desktop sessions: `archive_session` (the PR and branch remain)
  - Other routes: wind down with the shutdown method of whatever mechanism started it
- **Do not wind down**: sessions whose PR is OPEN / sessions still working (`isRunning: true`, no PR yet). Archiving also cleans up that session's worktree, so winding down before merging erases unmerged work
- A subagent ends by itself when it completes, so there is nothing to wind down. While one is running, tell the user before they `/clear` the orchestrator
