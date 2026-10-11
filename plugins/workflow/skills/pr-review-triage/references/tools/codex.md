# Codex (id: `codex`)

| Item | Details |
|---|---|
| Bot account name (full match on login) | `chatgpt-codex-connector[bot]` |
| How it starts | Depending on settings, reviews automatically on PR creation. In repos with automatic review turned off, request with the comment `@codex review` |
| Done signal | A review (with findings) |
| "No findings" signal | A 👍 reaction on the PR (does not appear in reviews). 👀 means reviewing |
| Rate-limit / quota signal (not reviewed) | A usage-limit comment ("usage limit", "couldn't run") |
| Wait time | Not stated. A limit gets no response to our requests, so ask the user to lift it |
| Heavy findings | P1 |
| How to request a re-review | Comment `@codex review` (combined into one comment with requests to other tools). Any focus must be short English only (below) |
| Command to run locally | `codex exec` (Codex CLI) |

## Notes

- **Unverified: whether a label can exclude it from automatic review** (`review:light` with `review-auto: on`). If not, Codex runs even on light PRs whenever automatic review is ON
- **Codex does not auto-resolve threads that were fixed.** They stay unresolved even when fixed, so don't judge progress by `isResolved` (the response table in the PR body is the record).
- **Focus must be short English only** (measured 2026-07-29). Adding long Japanese focus text after `@codex review` can make it not respond. Measured on the same PR and commit:

| Posted body | Codex's response |
|---|---|
| `@coderabbitai review` + `@codex review` (bare) | Replied in 4 minutes (1st) |
| `@codex review <Japanese focus text, 200+ chars>` | No response after 85 minutes (2nd) |
| `@coderabbitai review` + `@codex review` (bare, reposted) | Replied in 4 minutes (3rd; found one P2) |

  It replied as soon as the comment went back to bare, so we concluded the long focus text was suppressing the trigger (no other commit in between). Allowed is short English like `@codex review for transaction correctness`. If a long explanation is needed, post an explanation comment that doesn't mention the bot first, then a comment with the mention only.
