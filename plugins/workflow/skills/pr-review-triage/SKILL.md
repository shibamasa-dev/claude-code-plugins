---
name: pr-review-triage
description: Run right after creating a PR or pushing to one. Sorts the diff by weight to pick the reviewer, then runs request -> wait -> evaluate and fix -> re-review. Light PRs (docs only such as README, up to 200 lines) are reviewed by Claude with the code-review skill, recorded in the PR body, then only CI is awaited. Heavy PRs (code, config, behavior-defining docs such as skills/hooks, over 200 lines) go to the repo's review tools (CodeRabbit, Codex, Copilot, Gemini, Cursor Bugbot, etc.) via connectors (if the tools' automatic review is ON, don't request; just exclude light PRs via the `review:light` label), then results are evaluated and handled, with a response table in the PR body. Also decides on and sends re-review requests. Use when the user says "PR created", "opened a PR", "pushed", "review", "re-review", "request review", or in Japanese 「PR 作った」「push した」「レビューして」「レビュー待って」「レビュー来た？」「再レビュー投げて」「重めでレビューして」. Always run after creating or pushing to a PR, even without being asked.
last_reviewed: 2026-10-10
review_after: 2027-04-10
---

# pr-review-triage — sort PR reviews by weight and run them

> The canonical source for stages 5 and 6 of dev-flow in the same plugin (request, wait, evaluate and fix, re-review). Per-tool differences (account name, how to request, signals for done and not reviewed) live in [references/tools/](references/tools/), one file per tool. The Monitor used for waiting locally is in [references/monitor-snippet.md](references/monitor-snippet.md).

**Premise**: repos handle the tools' automatic review in one of two ways (`review-auto:`, decided in 1).
- **`off` (default)**: the tools' automatic review is turned off. Left on, the tools run even for a one-line README fix, and light PRs eat up the plan's limit (runs per hour). In exchange, this skill decides who to ask for each PR and asks
- **`on`**: the tools' automatic review stays ON. Only light PRs get the `review:light` label when created, and the tool's settings exclude them from automatic review (2.1). Heavy PRs run automatically, so don't request. A manual `@coderabbitai review` also counts once against the limit, so turning automatic review off saves no quota. CodeRabbit does not count PRs excluded from automatic review (by label, etc.) against the limit ([rate limits](https://docs.coderabbit.ai/management/rate-limits))

**When to run**: right after creating a PR (as dev-flow-gate prompts), right after pushing to an existing PR (decide by the criteria in 6 whether to request a re-review), when the user explicitly asks for a re-review, and when a rate limit has cleared.

**Waiting differs between cloud and local**: a cloud session subscribes to PR events (`subscribe_pr_activity`) and ends the turn. Locally, start a Monitor. Monitor runs shell commands, so it uses `gh` inside (the exception where the CLI stays because connectors are unavailable). **Monitor only runs while the session is alive.** If the user will be away for a long time, tell them "closing the session also stops waiting for reviews".

## 1. Decide which tools to use

```bash
export CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY='${user_config.review_heavy}' CLAUDE_PLUGIN_OPTION_REVIEW_LIGHT='${user_config.review_light}' CLAUDE_PLUGIN_OPTION_REVIEW_AUTO='${user_config.review_auto}'
D=${CLAUDE_PLUGIN_ROOT}/skills/pr-review-triage/scripts/detect-bots.sh
bash $D          # tools to use for heavy PRs
bash $D --light  # what to use for light PRs (claude and tool ids; either one, or both)
bash $D --auto   # the tools' automatic review (on / off)
```

`$D` in later sections is this path (when running in another shell, define it again together with the environment variables).

Run it inside the repo's working tree. For each key, the first one found from the top wins (the result is not saved):

1. A line in the repo's CLAUDE.md (or AGENTS.md)
2. userConfig

| Line | userConfig | Example | Meaning |
|---|---|---|---|
| `review-heavy:` | `review_heavy` | `coderabbit, codex` | Tools for heavy PRs (comma-separated). `none` means "no tools" |
| `review-light:` | `review_light` | `claude` | What to use for light PRs. Default `claude` (Claude reviews, per step 3). Writing tool ids treats light like heavy (no label; those tools, per step 4). Listing both, like `claude, codex`, means Claude reviews (3) and the listed tools' results are also awaited |
| `review-auto:` | `review_auto` | `on` / `off` | Whether the tools' automatic review is ON. Default `off` |
| `review-notes:` | — | Natural language | What reviewers should focus on. Read the line as is (the script does not read it) |

- **Ids are printed**: the tools to ask this round. An id is a file name in `references/tools/<id>.md`
- **Nothing printed, exit 0** (`review-heavy: none`): a repo without tools. Even heavy PRs are reviewed by Claude per step 3 (`review-light: none` also uses step 3)
- **exit 4** (no `review-heavy:` line and no setting): ask the user which tools to use, and propose a PR that adds a `review-heavy:` line to the repo's CLAUDE.md
- **exit 5** (a line or setting exists but cannot be read: a typo with no known id, or `review-auto:` other than `on` / `off`): do not treat it as "no tools" or "off". Show stderr to the user and ask what they meant (this prevents a mistyped `none` from producing PRs that nobody reviews)

**`review-notes:`** is not used for sorting (2). It goes to two places:
- Claude's review (3): pass it to `code-review` as focus
- Requests to tools (4.1): do not mix it into the mention lines of the request comment. Post it as an explanation comment without mentions before the request comment (Codex stops responding to long focus text; see `references/tools/codex.md`). In rounds where `review-auto: on` means no request is made, there is nowhere to pass it, so put anything the tools should always know in the tools' own settings

**Do not guess from bots that showed up on past PRs.** With automatic review turned off, light PRs leave no bot trace, so the guess comes out empty and some PRs get no review at all.

## 2. Sort

```bash
git fetch origin <base>
git diff --numstat origin/<base>...HEAD | bash ${CLAUDE_PLUGIN_ROOT}/skills/pr-review-triage/scripts/classify.sh
```

The input is the local diff (no `gh`; cloud sessions also have a local clone). Line 1 is `light` / `heavy`; the following lines are reasons. The decision is deterministic: the same diff gives the same result.

**heavy** (any one of these makes it heavy. When in doubt, lean heavy: a miss costs more than one tool run):
- Contains files other than documents (`.md` `.markdown` `.txt` `.rst` `.adoc`), including files without an extension (such as `.gitignore`) and binaries
- Documents with `skills/` `hooks/` `agents/` `commands/` `rules/` `.github/` in the path, or named `SKILL.md` `CLAUDE.md` `AGENTS.md`. In plugin repos these md files are the content itself, and a one-line change alters agent behavior
- Total changed lines (added + deleted) over 200. A rough limit on what can be read at once without findings getting less accurate
- Empty diff (fetching it may have failed)

**light**: everything else (docs only such as README, up to 200 lines).

Even for light, if the user asks for a heavier review (e.g. 「重めでレビューして」), run the heavy steps (4) (leaning heavier is fine; never lean lighter). If the `review:light` label is set, remove it before requesting (same as 5).

The maintainers check changes to these criteria against diffs taken from real PRs, in an eval set kept locally under `evals/` (git-ignored, not shipped with the plugin).

### 2.1 With `review-auto: on` — decide the label before creating the PR

In `review-auto: on` repos, set the label when creating the PR (setting it afterwards may be too late for the tool's first automatic review). So run 1 and 2 **before creating the PR** (dev-flow stage 4 also points here).

1. Create it with the `review:light` label only when `bash $D --auto` is `on`, the decision in 2 is `light`, and `bash $D --light` includes `claude` (or prints nothing). Otherwise, no label
   - **Repos that list tools in `review-light:`** (e.g. `review-light: coderabbit, codex`): no label even for light. The tools' automatic review runs as is, handled like heavy (step 4; the tools to wait for are the ids from `bash $D --light`). This is also how to back out of the label setup
   - **Repos that list `claude` together with tools** (e.g. `review-light: claude, codex`): set the label. Tools the label excludes (CodeRabbit) don't run, and tools it can't exclude (Codex, etc.) run automatically. List only tools that can't be excluded. If you list one that the label excludes, no result arrives automatically, so request it manually via 4.1, as in "When tools are listed too" in 3
2. Create the label first if the repo doesn't have it: `gh label create review:light --force --description "Light PR. Excluded from the tools' automatic review"` (`--force` just overwrites if it already exists)
3. Create the PR with `gh pr create --label review:light ...`. The GitHub connector's `create_pull_request` cannot set labels, so this is an exception that uses `gh`
4. Configure the tool to exclude PRs with this label from automatic review. CodeRabbit's example config and unverified points are in [references/tools/coderabbit.md](references/tools/coderabbit.md). Tools the label can't exclude run even on light PRs (unverified for Codex; see `references/tools/codex.md`)

After creating the PR:
- **light (with label)**: follow 3 as is (if `claude` is listed with tools, "When tools are listed too" in 3)
- **heavy**: the tools run automatically, so don't post the 4.1 request comment. 4.2 to 4.4 are unchanged. For "the head SHA and time noted in 4.1" in 4.4, read the head SHA and time at PR creation instead (`head.sha` and `created_at` from `pull_request_read` `get`)

## 3. light — Claude reviews and only CI is awaited

1. Start the built-in `code-review` skill with the PR number (e.g. `code-review <PR number>`; pass `review-notes:` as focus if present). Not `coderabbit:code-review` (that one uses CodeRabbit's quota). Don't add `--comment` (we don't write in threads). Where `code-review` is unavailable, give `git diff origin/<base>...HEAD` to a general-purpose subagent to review
2. Write the result in the **PR body** under a `## Review (Claude)` section as a response table (finding / verdict / action / basis). **Even with zero findings, keep the section and write "No findings"** (so later readers don't misread it as "not reviewed"). Older PR bodies may have `## レビュー（Claude）` instead, which counts too. Update the body with the connector's `update_pull_request`
3. Fix the findings you accept and push. Don't ask the tools (see below when tools are also listed in `review-light:`)
4. **Wait only for CI**: in the cloud, `subscribe_pr_activity`; locally, run "Wait only for CI" from [references/monitor-snippet.md](references/monitor-snippet.md) in a Monitor. Finishing without waiting gets stopped by dev-flow-gate's Stop check. If it exits with `NO_CHECKS` because no check was ever attached, do not count CI as green; report "this repo (this commit) has no checks". If it exits with `FETCH_GAVE_UP` after repeated fetch failures, report CI as "unverified" and do not move on to the merge decision until a re-fetch gives a result

**When `review-light:` lists `claude` together with tools** (e.g. `review-light: claude, codex`): in addition to 1 to 4, wait for the listed tools' results (ids other than `claude` from `bash $D --light`) via 4.2 to 4.4, evaluate them in 4.5, and add them to the response table. With `review-auto: on`, don't request tools the label can't exclude (Codex, etc.); wait for their automatic review (for the head SHA and time in 4.4, use the substitution from 2.1). If you listed a tool the label excludes (CodeRabbit), no result arrives automatically, so request it manually via 4.1 (don't keep waiting). With `off`, request all of them via 4.1. The Monitor author filter is `bash $D --light --regex`.

In `review-heavy: none` repos, run heavy PRs through the same steps and also write in `## Review (Claude)` why it was heavy (the classify.sh reason lines).

## 4. heavy — request tools -> wait -> evaluate and fix

### 4.1 Request

In `review-auto: on` repos, don't request right after creating the PR (2.1). Otherwise, request as described under "How to request a re-review" in `references/tools/<id>.md` (same for the first time). **Right before requesting, note the current head SHA (`head.sha` from `pull_request_read` `get`) and the time** (to separate this round from earlier results in 4.4).

- **Tools requested by comment**: post **one combined comment** with the connector's `add_issue_comment` (e.g. `@coderabbitai review` and `@codex review`, one per line). The body is mention lines only (focus constraints are in each tool's file; Codex takes only short English)
- **Copilot**: the connector's `request_copilot_review`
- Do not post from a script via `gh`

### 4.2 Sweep existing results first

**Required.** Monitor and subscriptions only catch events after they start. If you miss results that arrived before the request, you keep waiting for results that never complete.

- Unresolved threads: the connector's `pull_request_read` (`get_review_comments`). **Do not filter by author** (so unexpected authors aren't missed; only the Monitor filter narrows to tool accounts)
- Reviews and comments: `pull_request_read` (`get_reviews`, `get_comments`)
- Reactions (Codex's 👍, etc.): not available from the connector, so `gh api repos/OWNER/REPO/issues/N/reactions`

Evaluate and handle any findings right away without waiting. If a "no findings" signal has arrived, count that tool's result as in. If it is a rate-limit or quota signal, treat that tool as **not reviewed** and go to 4.4.

### 4.3 Wait

- **Cloud**: subscribe to PR events with `subscribe_pr_activity` and end the turn
- **Local**: start a Monitor (`persistent: true`). The implementation is in [references/monitor-snippet.md](references/monitor-snippet.md). The author filter is the output of `bash $D --regex` (with the same environment variables as in 1; when light runs with tools, `bash $D --light --regex`). **Exclude everything other than the tools (your own replies).** Picking up your own posts floods notifications and buries the real reviews

Notification bodies are truncated, so when something new is detected, always re-fetch the full text before evaluating. Even if the timeout notification shows 0 items, don't read it as "nothing yet"; re-check the primary source.

### 4.4 Deciding results are in

- Stop waiting when results from **every tool requested this round** are in. A result is a review (with findings) or a "no findings" signal (per-tool signals are in `references/tools/<id>.md`). Don't stop waiting on partial results (you may evaluate and implement the findings that arrived first while waiting for the rest)
- **Don't count results from an earlier commit or round.** Count only reviews whose `commit_id` matches the head SHA noted in 4.1 and that were submitted (`submitted_at`) after the noted time; count "no findings" reactions and status comments (walkthrough, etc.) only if they came after the time noted in 4.1. If a review of an earlier push, a review from before re-requesting on the same head, or an earlier round's 👍 ends the wait, you read "all in" while nobody has looked at the current diff
- **A rate limit or quota is "not reviewed".** Don't count it as a result; wait again. Counting it as "no findings" leads to reporting a PR nobody reviewed as "ready for a merge decision"
  - Rate limit with a wait time: once the stated time has passed, re-request **only that tool** and wait again. This is outside the re-review criteria in 6 (no review has arrived yet)
  - Plan or usage limit, or waiting on an on-demand button: re-requesting gets no response, so tell the user "<tool> hit its limit and has not reviewed" and ask them to lift it. Once lifted, wait again

### 4.5 Evaluate and fix

- External reviews are "suggestions", not "orders". Check them against the actual codebase, decide which to act on, implement those -> run the repo's checks (tests, lint, etc.) -> commit and push. **Decide whether a finding is valid by measuring, not by guessing** (don't wave it off with "this condition shouldn't trigger")
- **For findings based on a convention, always open the cited source yourself** (depending on how the quote was cut, the finding may rest on a convention for a different column or section than the target)
- **Don't reply in threads.** Replying makes the tool auto-respond and the thread grows. It is also redundant, since the commit and PR body show it
- **Write a response table in the PR body** (four columns: finding / verdict / action / basis; don't abbreviate). `isResolved` is unreliable (some tools don't auto-resolve). Since you don't reply either, the response table is the only human-readable record of what was done
- **The PR body starts with a two-column "before -> after" table** (one row per aspect). Even for doc-only PRs without implementation, write "undefined -> decided this". Acceptance criteria ✅/❌, the response table, and out-of-scope notes go below it
- **`## Out-of-scope notes` has three columns: note / disposition / basis** (older PR bodies may name it `## スコープ外の気づき`). The disposition is one of "layer (stack with `gh-stack`) / issue #N / won't do". Fill every row before merging

### 4.6 Report

Two parts: "addressed / not addressed (with reasons)". Start with each tool's result (number and severity of findings, the commit it reviewed). Write "ready for a merge decision" only after confirming that every requested tool actually returned a review. If a tool has not reviewed, write something like "<tool> is rate limited and has not reviewed; re-requested", and don't ask for a merge.

## 5. After a push — sort again

After pushing (e.g. to address findings), redo the sorting in 2.

- **Still light**: if the light reviewer (`bash $D --light`) is only `claude` (or prints nothing), push and wait only for CI. If tools are included (even alongside `claude`), decide whether to ask them for a re-review by the criteria in 6, same as still heavy (the exception for pushes that add new work also applies)
- **Was light, now heavy**: remove the `review:light` label first if set (`gh pr edit <PR number> --remove-label review:light`). With `review-heavy: none` (`bash $D` prints nothing), Claude reviews per step 3. If there are tools, this is their first time, so request per step 4 regardless of the criteria in 6. It is unverified whether removing the label starts the tools' automatic review, so even with `review-auto: on`, request manually per 4.1
- **Still heavy**: decide by the criteria in 6 whether to request a re-review. A push that adds new work other than addressing findings, after review results came back, is an exception to the criteria in 6 and gets a request

## 6. Re-review

**Request**: only when the findings fixed this round include **${user_config.rereview_threshold} or more** heavy findings (CodeRabbit=Critical / Codex=P1; for other tools, the Critical/High equivalent; each tool's name for them is under "Heavy findings" in `references/tools/<id>.md`) (userConfig `rereview_threshold`, default 3). Then request the tools asked this round (request as in 4.1, then continue from 4.2).

**Otherwise, don't request**: push, wait only for CI, and move to the merge decision. Requesting on every push leads to 5 rounds per PR, which costs too much (measured on a past case). Most tools don't re-review automatically on push, so waiting without requesting brings nothing.

In `review-auto: on` repos, if the tool's settings run a review automatically on every push (e.g. CodeRabbit's incremental review), don't request that tool; wait from 4.2 (so the same push doesn't use quota twice).

**Exceptions to the criteria** (you may request even if the criteria aren't met):
- **An explicit instruction from the user** ("request a re-review")
- **A push that adds new work other than addressing findings, after review results came back.** Nobody has looked at the added part yet, so request regardless of the re-review criteria. A push that only addresses findings follows the usual criteria. Work added before results came back is covered by the first review
- **Re-requesting after a rate limit clears** (4.4; only that tool)
- **PRs created by an agent (a delegated session, etc.) in an auto-merge repo** (the repo's `.claude/dev-flow.json` is `{"autoMerge": true}`). That repo already allows merging itself to be decided by someone other than the user, so the re-review before it is treated the same way. Follow the repo's CLAUDE.md if it sets a rule; otherwise lean toward requesting when there are many critical/actionable findings (excluding nits and style) or the PR touches many files. Don't measure by total comment count (tools produce endless nits)
  - Not covered (needs the criteria or an explicit instruction): PRs in client / product repos (including other organizations' repos) / PRs not created by an agent / PRs with breaking or hard-to-reverse changes

## Merge

- **Merge (and asking for a merge) only after results from every tool requested this round are in** (even when the user has delegated merging). Rate limits and quotas don't count as results. Merging on a partial 👍 or zero findings misses findings from other tools that arrive later (real case: right after merging on a 👍, another tool's Major finding arrived and had to be fixed in a follow-up PR)
- **Hand to the user**: findings where design judgment is split / findings that change the spec or policy / findings about real harm in code you didn't write / **merging** (merging is always the user's decision)
- **Exception: auto-merge repos** (the same repos as the exception in 6) are the only place the agent may merge on its own judgment. After handling one review round, the agent decides "re-review or merge". If the repo has its own document (e.g. `.claude/ARCHITECTURE.md`), that is the canonical source for the judgment criteria and where to run it. Client / product repos, breaking changes, and hard-to-reverse changes are excluded and still go to the user

## Don'ts

- Request on every push / commit without meeting the re-review criteria (except the exceptions in 6)
- Extend the auto-merge repo exception to repos without auto-merge, or to PRs not created by an agent
- Request "just to be safe" without meeting the criteria
- Request again because nothing came after a few minutes (leave waiting to 4.3)
- Request on closed / merged PRs
- Manually change the sorting result to light because it "looks light" (if you want to change it, open a PR that fixes classify.sh's criteria). Leaning heavy (the user's "review it heavier") is fine
- Count a tool stopped by a rate limit or quota as "reviewed"
