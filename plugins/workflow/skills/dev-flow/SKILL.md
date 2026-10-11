---
name: dev-flow
description: Entry procedure that runs one development flow from request to merge, for both issue work and verbal implementation requests (structural-change check and architecture review, self-review after implementing, PR body markers, waiting for review and re-review, merging after writing `## Result`, auto-merge repos). Use for "work on issue", "implement", "fix", "open a PR", "ready to merge?", or in Japanese 「この issue やって」「#12 対応して」「〜を実装して」「〜を直して」「PR 作って」「マージして」「マージしていい？」. Always read before starting any request that changes code or plugins.
last_reviewed: 2026-10-06
review_after: 2027-04-06
---

# dev-flow — entry point of the development flow

> This is the source of truth for the order of the steps and for the agreements that span steps. The detailed procedure inside each step belongs to the skill named for it. If that skill is not installed, use the minimum procedure written here instead.

## The 9 steps

| Step | What to do | Detailed procedure |
|---|---|---|
| 1. Take the request | Tell an issue from a verbal request | issue-ops |
| 2. Structural-change check | If it is a structural change, get a GO from architecture review. Do not open an implementation PR before the GO | this SKILL |
| 3. Implement and verify | Run the repo's checks and reread your own diff | this SKILL |
| 4. Open the PR | Put `Closes` / `Refs` and `Arch-Review:` in the body | this SKILL |
| 5. Wait for review and CI | Route by how heavy the diff is (light: Claude reviews; heavy: ask the review tools), then wait for those results and CI | pr-review-triage |
| 6. Evaluate and fix findings | Check and judge each finding, keep a response table in the PR body. If you fixed at least the threshold number of heavy findings, re-review → back to 5 | pr-review-triage |
| 7. Write `## Result` | Write it in the body of the issue that `Closes` points to | issue-ops |
| 8. Propose the merge | Propose once, when the conditions are met | this SKILL |
| 9. Merge | Merge on the user's instruction. In an auto-merge repo, merge yourself | this SKILL |

## 0. Check first (only once per repo in the same session)

1. **Issue Fields**: call `list_issue_fields` (with owner and repo).
   - An organization repo without `Arch Review` or `Verification` → warn the user once: "If you register the Issue Fields `Arch Review` (Pending / Approved) and `Verification` (Not needed / Pending / Verified) in the organization settings, the architecture review and real-environment verification states can be kept on issues." Until they are registered, get the GO in chat and write unverified items in `## Result`.
   - A personal-account repo (cannot be resolved as an Organization, or returns empty) → tell the user once that Issue Fields are organization-only and unavailable, and proceed with the same fallback.
2. **Auto-merge**: read `.claude/dev-flow.json` on the repo's default branch (with a local clone, `git show origin/<default branch>:.claude/dev-flow.json`; otherwise `get_file_contents` without a ref). Do not decide from the working branch's value (so that a PR enabling auto-merge is not auto-merged by that branch's own value). `{"autoMerge": true}` means an auto-merge repo (step 9). If the file is missing or `false`, the user merges as usual.
3. **Review tools**: follow pr-review-triage's rules (the `review-heavy:`, `review-light:`, `review-auto:` lines in the repo's CLAUDE.md / AGENTS.md; otherwise userConfig `review_heavy`, `review_light`, `review_auto`. If neither names a heavy tool, ask the user. Do not guess from past PRs).

## How to ask the user to decide

Things the user decides (whether to make an issue, the GO from architecture review, whether to merge, and so on) are offered as choices, not buried in prose. Prose is easy to miss.

- If the session has a tool for presenting choices, use it. Examples: Claude Code's `AskUserQuestion`, the choice cards in a project thread.
- Offer 2–4 choices and mark one as recommended. Add one line to each choice saying what happens if it is picked.
- In environments without such a tool (headless runs, etc.), ask in text. Put the question on the first line, list the choices one per line, and mark the recommended one.
- While waiting for the answer, you may continue reversible work along the recommended choice, as long as it does not break the step's constraints. While waiting for a GO on a structural change, do not start implementing that change; only investigate, discuss the design, and write design comments (step 2). Do not perform irreversible operations (merge, delete, etc.) until the answer arrives.

## 1. Take the request

- **From an issue**: read the body with `issue_read`. Check the acceptance criteria and the Issue Field `Arch Review`.
- **Verbal request**: if it needs several steps to finish, propose making an issue before starting (how to write it: issue-ops). If it is a one-off that one PR finishes, proceed without an issue and write `Refs: none (verbal request)` in the PR body. The result is recorded in that PR body.

## 2. Structural-change check

**Structural changes that need a GO**:

- Adding or removing a plugin, skill, hook, mod, command, or MCP server
- Changing plugin boundaries (moving, splitting, or merging parts; adding references between plugins)
- Changing agreements that others rely on (userConfig keys, PR body format, markers that hooks read, file locations)
- Adding a blocking condition to an existing hook

**Not covered**: rewording existing skills, bug fixes that keep the agreements, changes to tests or docs only.

- If the issue has `Arch Review` set, its value overrides your judgment. `Pending` means no implementation PR. `Approved` means the GO is given.
- A structural change without a GO: if Issue Fields exist, set `Arch Review: Pending`, write the chosen approach and design requirements in the issue body (or a design doc if large), and ask the user for a GO. Until the GO, only investigation, design discussion, and design comments are allowed.
- When in doubt, treat it as a structural change. Design decisions you made yourself (boundaries, references between parts, deletions) are laid out in the issue for confirmation before the PR.
- The gate is lifted when the user changes it to `Approved` or gives an explicit GO.

## 3. Implement and verify

- Run the repo's checks (whatever CONTRIBUTING, the PR template, and the CI config list: tests, lint, validators, version and CHANGELOG checks).
- **Reread your own diff** (`git diff origin/<base>...HEAD`). Read it as if looking for reasons CI or a reviewer would reject it:
  - Changes nobody asked for, leftover debug output
  - Personal paths, email addresses, specific personal names or internal proper names (especially in a distributed repo)
  - Missing updates to version, CHANGELOG, README
  - Behavior changed without tests
- Fix what you find before opening the PR.

## 4. Open the PR

**Before opening a new PR, check its granularity.** Many review tools count their limits by PRs opened or pushes, so more PRs use up more quota.

- **One open PR per issue.** Follow-ups for the same issue (doc additions, small fixes) are pushed to the open PR. A new PR is allowed only in these two cases
  - After the previous PR is merged or closed
  - When stacking a separate concern that depends on the current branch as a `gh-stack` layer (whether it becomes a layer or an issue is decided in issue-ops)
- **If, after review results came back, you add new work other than responses to findings, request review again with that push.** Nobody has looked at the added part yet, so request it regardless of pr-review-triage's re-review threshold (number of heavy findings fixed). A push that only responds to findings follows pr-review-triage's threshold. Anything added before the review comes back is included in the first review as is
- **Aim for 500–800 lines (additions + deletions).** Review accuracy drops on PRs that are too large. If it will exceed that, split into a `gh-stack` layer only where there is a boundary that can be cut off as a separate concern depending on the current change. If there is no such boundary (one concern that breaks if split), open it as one PR and explain in the PR body why it is large. Do not invent dependencies just to create layers

Create it with the connector's `create_pull_request`. If the repo has a PR template, follow its headings. The body must contain these two (if the dev-flow-gate hook is installed, it blocks without them):

- **`Closes #N` or `Refs #N`** (`owner/repo#N` for another repo)
  - `Closes`: a PR expected to turn every acceptance criterion of the issue ✅. Merging closes the issue, so always write step 7's `## Result` before merging.
  - `Refs`: only part of the acceptance criteria. Write "unmet items" and "where the leftovers go (layer / issue number / won't do)" in the PR body. Merging does not close the issue. The post-merge cleanup (step 9 below) belongs to the session that made the request.
  - Verbal request with no issue: `Refs: none (verbal request)`
- **One `Arch-Review:` line**
  - Not a structural change: `Arch-Review: not-needed — <reason>`
  - Structural change with a GO: `Arch-Review: approved — <where the GO is (link to the issue, design doc, or message)>`

**In repos where the tools' automatic review is ON (`review-auto: on`), route before opening the PR.** Following pr-review-triage 2.1, if it is light (and `review-light:` includes `claude`), open it with the `review:light` label. Adding the label after opening may be too late for the tool's first automatic review. The connector's `create_pull_request` cannot pass labels, so only in this case open it with `gh pr create --label review:light`.

## 5–6. Wait, evaluate, fix

The procedure is in pr-review-triage (routing, how to request, how to wait, detecting arrival, evaluation, the response table, re-review). Only the agreements that span steps are here:

- **Route by how heavy the diff is.** For a light PR (docs only, up to 200 lines), if the light reviewer (`review-light:`, default `claude`) includes `claude` (or is `none`), Claude reviews it and writes the review in the PR body under `## Review (Claude)`. If it includes a tool, also wait for that tool's results, as for a heavy PR (both if both, as in `claude, codex`). Then wait for CI. For a heavy PR, ask the repo's review tools through the connector (in repos with automatic review ON, don't ask), and wait for those results and CI. In a `review-heavy: none` repo, Claude reviews heavy PRs too.

- **Waiting differs between cloud and local.** A cloud session ends its turn after subscribing to PR events (`subscribe_pr_activity` if available). The events wake it up across turns. Locally, start a Monitor. A Monitor runs shell commands, so use `gh` inside it (the exception where the CLI remains because connectors cannot be used).
- **A tool stopped by a rate limit or quota counts as not reviewed**; after the wait, re-request only that tool.
- **Re-review only when you fixed at least the threshold number (userConfig `rereview_threshold`, default 3) of heavy findings (Critical / P1 level)**, and request it from the tools asked in that round. Otherwise push and wait only for CI. Either way, go back to step 5.
- Do not reply to threads about findings; write the response in the PR body's response table (finding / verdict / action / evidence).

## 7. Write `## Result`

- Write `## Result` (1–5 lines: conclusion / what was done and not done / related PR) at the end of the body of the issue that `Closes` points to. How to write it, and `## Notes for next time` for recurring tasks, are in issue-ops. Older issues may use `## 結果`, which is still accepted.
- Updating the body replaces it entirely, so get the current body with `issue_read`, then pass the full text with the addition at the end to `issue_write` (update).
- If acceptance criteria remain that can only be checked in the real environment, write them in `## Result` as "not done (intentionally)", and if Issue Fields exist, set `Verification: Pending`.
- **Write it before merging**. If you write it after the merge auto-closes the issue, the close has no record.

## 8. Propose the merge

When the following are all met, propose "ready to merge" to the user once. Present it as described in "How to ask the user to decide", as choices (e.g. merge / keep waiting). In an auto-merge repo (step 9), go straight to step 9 without proposing. Propose only for PRs that step 9 says go to the user:

- Review is done:
  - Heavy PR: every review tool asked in that round has produced results (rate limits and quotas don't count). With `review-heavy: none`, the PR body has `## Review (Claude)`
  - Light PR: if the light reviewer (`review-light:`) includes `claude` (or is `none`), the PR body has `## Review (Claude)`. If it includes tools, all of them have produced results (rate limits and quotas don't count). Both if both
  - Older PR bodies may have `## レビュー（Claude）`, which counts too
- Responses to findings are done and the PR body's response table is up to date
- CI has finished green and there are no merge conflicts (in a repo where no checks run at all, don't count it as green; write "no checks" in the proposal)
- `## Result` is written in the issue that `Closes` points to (for a verbal request without an issue, the result is in the PR body)

Include in the proposal (in the explanation before the choices; for a card, in its description):

- Link to the PR
- Status per review tool (e.g. `<tool name>: 2 findings, addressed`, `<tool name>: no findings`). Write "not reviewed" for any stopped by a rate limit
- CI result, and the issue where `## Result` was written (for a verbal request without an issue, the PR body that holds the result)

While waiting, wait quietly. A push that only changes `version` and CHANGELOG (e.g. merging in main) may wait only for CI without re-requesting review.

## 9. Merge

- **By default the user merges** (if the user explicitly tells you to merge, Claude may merge).
- **Auto-merge repo** (`.claude/dev-flow.json` is `{"autoMerge": true}` in step 0): once step 8's conditions are met, Claude merges with `merge_pull_request`. If the repo's own docs (CLAUDE.md, `.claude/ARCHITECTURE.md`, etc.) define criteria and where to run it, follow them. If the repo allows GitHub auto-merge, you may hand the CI wait to GitHub with `enable_pr_auto_merge`. But send these to the user:
  - Breaking or hard-to-reverse changes (data migrations, removing public APIs, etc.)
  - PRs Claude did not create
  - PRs in client / product repos (including other organizations' repos). Same treatment as pr-review-triage's auto-merge exceptions
- **Enabling auto-merge**: when the user says "auto-merge in this repo", open a PR that adds `{"autoMerge": true}` to `.claude/dev-flow.json`. It takes effect when the user merges that PR. To stop it, set `false` or delete the file.
- After the merge: for an issue referenced with `Refs`, the session that made the request adds this round's part to `## Result`. Do not close it while unmet acceptance criteria remain on that issue. Close it after the leftovers are done, moved to another issue, or decided against. If only items checkable in the real environment remain, say so in `## Result`, set `Verification: Pending` if Issue Fields exist, and you may close it. Keep the local clone following main (automatic if guards' git-freshness is installed).

## GitHub operations (connector first)

Use the GitHub connector's tools for GitHub operations. Use `gh` only for what the connector cannot do.

| Operation | Connector | When to use `gh` |
|---|---|---|
| Read, create, update, close issues | `issue_read`, `issue_write` | In environments where `issue_write` shows an approval form (issue-ops) |
| Issue comments, parent/child | `add_issue_comment`, `sub_issue_write` | Same as above |
| Create, update PRs | `create_pull_request`, `update_pull_request` | Creating with or removing the `review:light` label in `review-auto: on` repos (the connector cannot pass labels) |
| Read PRs, reviews, CI | `pull_request_read` (get, get_reviews, get_review_comments, get_comments, get_check_runs) | — |
| Merge | `merge_pull_request`, `enable_pr_auto_merge` | — |
| Wait for review locally | — | Inside a Monitor (it runs shell commands) |

`git` (commit, push, merging in main) is a local operation, so keep using the CLI.

## Don'ts

- Open an implementation PR on an issue with `Arch Review: Pending` (or waiting for a GO)
- Count a tool stopped by a rate limit or quota as "reviewed"
- Merge, or propose merging, without writing `## Result` in the issue that `Closes` points to
- Merge a PR in a repo that is not an auto-merge repo without the user's instruction
