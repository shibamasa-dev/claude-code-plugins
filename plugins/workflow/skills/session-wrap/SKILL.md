---
name: session-wrap
description: Check for leftovers before closing a session. Use when the user says "wrap up", "I'm done for today", "check what's left", or in Japanese 「閉じたい」「セッション終わる」「今日はここまで」「wrap up」「残件確認して」「片付けて終わる」. Mechanically collects the invoking session's own uncommitted changes, unpushed commits, open PRs, unreflected issues, and running subagents / Monitors, then proposes "do now / leave for next time / discard" for each item before closing. When every requested task is done, use it on your own without being asked, and if nothing is left, finish by asking in a choice dialog "Archive this session?".
last_reviewed: 2026-09-22
review_after: 2027-03-21
---

# session-wrap — check for leftovers before closing

This covers **only the session that invoked this skill**. If it isn't called, nothing happens (Claude has no way to act at the moment of `/exit`), but uncommitted changes stay on disk, issue-writeback state survives a resume, and subagent output stays in files. Only Monitors (waiting for PR reviews) are lost.

## Steps

1. **Collect mechanically** (no judgment):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/session-wrap/scripts/survey.py
   ```
   The session_id is resolved automatically by matching the pid of Bash's parent `claude` process against `claude agents --json`. If it can't be resolved, pass `--session <id>`.
2. **Count your own subagents / Monitors**: check what is running with `ListAgents`. A Monitor dies with the session, so if you are waiting for a review, tell the user "closing means the review won't be picked up" (the `pr-review-triage` rule).
3. **Propose one item per flag**, and act on the user's answer:

   | Flag | Proposal |
   |---|---|
   | `DIRTY` | Commit now (`commit-commands:commit`), leave for next time (if so, write what is uncommitted in the final report), or discard (`git stash` / `git checkout --`. **Destructive, so always confirm**) |
   | `UNPUSHED` | Push? (On a working branch, first check whether it is behind the default branch; if it is, merge that in before pushing. The guards plugin's bash-guard also blocks when it can count how far behind it is, but lets it through when it can't, so don't skip this check) |
   | `PR_OPEN` | If waiting for review, say "closing cuts off the Monitor". Is the response table written in the PR body? |
   | `PENDING_ISSUE` | If there are decisions, reflect them in the body/comments (`issue-ops`). If not, the `dismiss --why` the hook shows |
   | Running subagents | Wait for their reports, or stop them (output stays in files) |

   For items you proposed and got an answer on, **carry them out to completion inside this skill** (commit, push, issue write-back, dismiss). Don't push them to "later". The only things the skill doesn't decide on its own are "what to leave" and destructive operations.
4. **Temporary files**: the scratchpad is session-specific, so leave it. If you created verification files directly under `/tmp/claude-<uid>/` or inside the project, delete them (look back through the conversation to see what you created; the script doesn't know).
5. **Leave the handoff in a machine-readable place** (just saying "next time start from #92" in the conversation is forgotten by both the user and the next Claude). **Split leftovers into "this repo" and "other repos" before writing**.

   **(a) Leftovers in this repo — entry issue + handoff**
   - Items judged "left" **must be written into the entry issue's body** (`issue-ops`: "how things are now" = what is done and what to do next. Create an issue if there is none).
   - Write the entry into the handoff (the SessionStart hook injects it at the start of the next session in the same project):
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" write --entry owner/repo#92 --state "done up to X" --next "start with Y"
     ```
     A project can hold several entries (the same `--entry` updates, a different `--entry` appends; parallel sessions don't erase each other's entries). Keep the details in the issue body; the handoff is only a pointer.
   - The receiving side removes that one entry with `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" consume --entry <entry>` right after declaring it is starting on it (clean the moment it's picked up; if there is only one entry, `--entry` can be omitted). Sessions opened for unrelated work don't remove it, so it still shows in the next session. Entries older than 14 days are shown as stale.
   - **If "what to do next" remains, put it on `start_session` cards**: after writing the entry issue and handoff, call Claude desktop's `mcp__ccd_session__start_session` with `initiation: "own_initiative"`, one call per card; you decide how to batch the items (which items go into one card). It only shows a card; nothing runs until the user clicks it or tells you to start it (then call `start_session` again with just its `proposal_id`). **The card is where the user approves, so don't ask "Make cards?" in text first.**
     - **Don't split too finely. Batch by task size and dependencies** (making every small doc PR its own card multiplies parallel sessions and coordination work). Signs they belong together: they touch the same files / use the same shared resource (e.g. a shared test environment or shared DB) / have an order (B uses A's result) / each is small (a doc fix, a skill addition, done in one PR). Split only items that are large, can proceed independently, and share neither files nor resources. Aim for 1–2 cards per wrap.
     - If they run in parallel, put a turn-taking rule (locks, etc.) for shared resources and the ownership of shared files into the prompts.
     - Make the `prompt` a self-contained brief for a reader with zero background: the handoff entry (have it run `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" consume --entry <entry>` when it starts) and the entry issue (have it read `gh issue view <ref>` first), background, locations (paths of kits, samples, etc.), rules to follow (no direct DB changes, merging is the user's call, etc.), acceptance criteria, and scope (up to opening the PR).
     - With `context: "fresh"` (the default), only `prompt` and `background` (at least 80 characters of history) reach the new session; `context: "fork"` passes this whole conversation as well.
     - In environments where `start_session` is unavailable (CLI alone, cloud, etc.), don't make cards; just leave the handoff.
     - Write the title and task_id of each card you created in the final report. If it becomes unnecessary later, withdraw it with `dismiss_task`.

   **(b) Leftovers in other repos — don't write them in the handoff**

   The handoff is injected per project (by cwd). Writing another repo's entry injects unrelated instructions into this project's next session (noise). handoff.py's `write` mechanically refuses an `--entry` whose repo differs from the cwd's origin. Instead:

   1. **Open an issue in the target repo (required)** (`issue-ops`; "other repo" is a case where the leftover becomes an issue). Separate sessions can disappear when the machine restarts, so the durable record goes here.
   2. **Only for things that will be worked on soon**, **propose** starting a separate session in the target repo in a waiting state. If the environment has a skill or mechanism that can start another session in a waiting state without starting work right away, use it (if not, the issue from step 1 is enough): "Start a separate session in the target repo in a waiting state?" → start it **only after the user says OK**. A waiting session stops without starting work and moves when the user says "start". The seed must include the issue ref from step 1 and the scope "up to opening the PR (no merge, no deploy)". Even if the mechanism has a setting to start work immediately or run unattended, don't use it (it would start acting in another repo without permission checks).
   3. **The skill doesn't start one on its own** (the OK given on the spot counts as the "explicit instruction"). **Propose at most 1 per wrap** (waiting sessions left behind pile up, hit the limit on concurrently running sessions, and can stop other sessions from working). If you start one, write the session name in the final report.
6. **Final report** has two parts: "cleaned up / left". For what was left, separate this repo (the entry issue and handoff contents, the `start_session` cards created, by title and task_id) from other repos (issue refs, names of sessions started in a waiting state).
7. **Ask whether to archive**: if nothing is left ("left" is 0 items, or the leftovers are in issues and the handoff), after the final report **ask with `AskUserQuestion`: "Archive this session?"** (choices: archive / don't archive). On "archive", call `mcp__ccd_session_mgmt__archive_session` (`session_id: "self"`, a one-line `reason`). "Don't archive" signals more requests are coming, so clean nothing up and wait for the next instruction (when that request is done, run the wrap again).
   - **Don't ask** when: something is running in the background (Monitor, subagent, background Bash) / there are uncommitted or unpushed changes / review responses remain on your own PR. Clean those up first, or write in the report why they are left
   - Archiving ends the conversation, so call it only after the report and all issue and handoff writes are finished. Outside Claude desktop (environments without the tool), don't ask

## Don'ts

- `git stash` / `checkout --` / deleting worktrees without confirmation (never delete an unmerged worktree)
- Writing another repo's leftovers into the handoff (an unrelated entry gets mixed into this project's next session. Use `--force` only when you know it is another repo and intend to write it)
- Starting a separate session in a waiting state without the user's OK / starting 2 or more in one wrap
- Calling `start_session` with `initiation: "user_asked"` when the user didn't ask for a separate session (it starts immediately; use `own_initiative` so the user starts it from the card)
- Archiving the session without the user's OK (only when the dialog's answer is "archive")
- Piling up commits or pushes "just in case" when there is no flag
- Saying "nothing left" based only on the script's output (subagents and temporary files are outside the script)
