# Skeleton of a delegation prompt

The receiver **knows nothing of the history**. Assume it cannot read linked pages either, and write the facts it needs to decide (actual values, concrete examples) in the body.
**Write the full text for every batch.** Do not abbreviate by referring to another prompt, as in "rules are the same as batch A" (the receiver cannot see other prompts).
Fill in the `{}` and delete lines that do not apply. The project skill adds project-specific "Read first" and "Rules" lines.

```text
In {repo name} ({repo path}), please carry out the following batch.

## Read first
- gh issue view {entry issue number} -R {owner/repo} --comments
- (likewise for the other issues in the same batch)
- {the repo's convention files (CLAUDE.md, etc.)}

## Background
{Why now. Relation to the goal issue, deadline, where this sits in this cycle's minimum bar}

## What to do
{The batch's contents in order. If there are dependencies, state the order explicitly}

## Locations
{Input and output paths. Give exact paths for anything under gitignore}

## Rules
- Scope is up to creating the PR. Do not merge or deploy (merging is the user's decision)
  (Keep this line even for a batch that only verifies and changes no code. It is the upper bound if a fix turns out to be needed midway)
- Work on a branch / worktree cut from main. Do not use git add -A
- Update issues following the issue-ops skill; after creating a PR, wait for reviews following the repo's rules
- {Only when running in parallel: the turn-taking rule for shared resources (the mkdir lock) and ownership ranges within the same file}
- {Project-specific rules}
- Issue tool calls that do not depend on each other together in a single response

## Acceptance criteria
- {In a verifiable form. Not "works correctly" but "all tests in X pass" or "the count of Y matches when re-tallied from the output"}
- All tests within the reach of the change pass (write the range you ran in the PR body)
- Do not fix out-of-scope findings; write them in the PR body's `## Out-of-scope notes` section

## Interim reports (separate session only; delete this whole section for a subagent)
Reports go to the orchestrator session "{orchestrator session name}". Put this name as-is in SendMessage's `to`.
Text you only write in your own conversation does not reach the orchestrator. Send 1–3 lines at each of these points:
- When you start a long process (what, and when you expect it to finish)
- When you are stuck (waiting for a user's answer, a permission, a lock, or an error). Write the question as-is. The orchestrator relays it to the user
- When you create a PR (URL)

Do not ask the user questions in a dialog such as AskUserQuestion; send them by SendMessage to the recipient above (a dialog can only be answered on this session's screen, and the orchestrator cannot answer it). Only when SendMessage is unavailable (no tool, or it does not reach the recipient) ask the user directly in this session. While waiting for an answer, keep doing work that does not depend on the question.
The orchestrator relays the user's decisions. You may treat what the orchestrator passes on as "the user's decision" as a change to this prompt's instructions.
When SendMessage is unavailable, skip interim reports and write the final report, in the same format, at the end of your own conversation.

## Final report format
(Separate session: send it by SendMessage to the same recipient as above. Subagent: make your final response this format)
- What was done / what is left
- A reproduction command for each claim (mark claims you cannot give one for as "guess")
- PR URL
- Issue linkage: whether the PR body says Closes or Refs. If Refs, the reason (unmet acceptance criteria) and where the leftovers go
Right before writing the report, verify the claims once more.
```

## For a successor orchestrator

Send out the successor via a separate-session route (not as a subagent).

```text
In {repo name} ({repo path}), start {the project's weekly orchestrator skill name} and
continue from the plan section (<!-- weekly-orchestrator:plan --> …) of cycle issue {owner/repo}#{number}.
You are generation {N}. The previous generation handed over {when, and how far it got}.
Running batches: {batch numbers, routes, and any whose report recipient is still the old generation}
```
