# CodeRabbit (id: `coderabbit`)

| Item | Details |
|---|---|
| Bot account name (full match on login) | `coderabbitai[bot]` |
| How it starts | Reviews automatically on PR creation per the GitHub App settings. In repos with automatic review turned off, request with the comment `@coderabbitai review`. To keep it ON and exclude only light PRs, see "Using automatic review ON" below |
| Done signal | A review (with findings) |
| "No findings" signal | "No actionable comments" in the walkthrough (the auto-summary comment). With zero findings it creates no review and only writes completion inside this walkthrough |
| Rate-limit / quota signal (not reviewed) | "rate limited" (with a wait time) / "plan limit reached" |
| Wait time | For rate limited, the time written in the comment. A plan limit gets no response to our requests, so ask the user to lift it. The user clicks the on-demand review checkbox |
| Heavy findings | Critical |
| How to request a re-review | Comment `@coderabbitai review` (combined into one comment with requests to other tools) |
| Command to run locally | None |

## Notes

- **Pushing does not trigger a re-review automatically.** In repos where *Auto incremental reviews* is disabled, pushing a fix only returns `Review skipped / Auto incremental reviews are disabled on this repository` (measured). Waiting without requesting brings nothing.
- The walkthrough is updated on every push, so the Monitor doesn't notify its body; it only emits "No actionable comments" and the not-reviewed signals as status lines (`../monitor-snippet.md`). Not-reviewed signals can also come in a comment separate from the walkthrough.
- **Unverified**: whether the walkthrough shows "No actionable comments" when automatic review is off, a review is requested manually, and there are zero findings. Check on the first heavy PR and add the result here.

## Using automatic review ON (`review-auto: on`)

Exclude light PRs from automatic review with the `review:light` label. In the repo's `.coderabbit.yaml`:

```yaml
reviews:
  auto_review:
    labels: ["!review:light"]
```

Labels starting with `!` are negative matches ("Labels starting with '!' are negative matches"; [configuration](https://docs.coderabbit.ai/reference/configuration)). PRs excluded through automatic review controls don't count against the limit ([rate limits](https://docs.coderabbit.ai/management/rate-limits)).

**Unverified** (not measured, so not asserted; check on the first `review-auto: on` PR and add the result here):
1. Whether a label set when creating the PR excludes it before the first automatic review
2. Whether this setting can be applied per organization (if not, a `.coderabbit.yaml` per repo)
3. Whether automatic review starts after the label is removed (`pr-review-triage` assumes it doesn't and requests manually)
