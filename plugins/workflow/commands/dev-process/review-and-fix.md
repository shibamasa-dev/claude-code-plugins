---
description: Workflow that runs AI review -> evaluation -> fix plan -> implementation end to end
argument-hint: Optional review scope description
---

# Review and Fix Workflow

A workflow that runs AI reviews with multiple agents, evaluates the results, and makes the appropriate fixes. How findings are assessed is defined by `pr-review-triage`, not here; the project's CLAUDE.md comes first.

---

## Phase 1: Execute Review

**Goal**: Run parallel reviews with multiple agents

**Actions**:
1. Run the review script in the background:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/commands/dev-process/agent-review.sh [title]
   ```
   - The title is optional
   - Output files: `.context/workflow/review/{YYYYMMDDHHMMSS}_review[_{title}_by_{agent}].md`; the script's debug log goes to `.context/workflow/logs/`, and the script adds `.context/` to `.git/info/exclude`
   - **Important**: pass these parameters to the Bash tool
     - `run_in_background: true`
     - The codex CLI writes its session state under `~/.codex`, which is outside the sandbox's default write allowlist. Prefer having the user allow only `~/.codex` via `/sandbox`; pass `dangerouslyDisableSandbox: true` only when that limited allowance can't be used
2. The review script notifies its messages asynchronously, so end for now without waiting for the script to finish.

---

## Phase 2: Evaluate Review Results

**Goal**: Decide which findings to act on

**Actions**:
1. Read the review results from the output of Phase 1
2. Check for a failed review first. A reviewer that exited non-zero or wrote no output gets a `❌ <Reviewer> review FAILED (<reason>)` line, its text is an error (an authentication error, for example), not findings, and the script exits 1. If there is such a line, before assessing anything or making a fix plan:
   - Tell the user which reviewer failed and quote the first lines of its error output
   - Ask whether to re-run the review or continue with the other reviewer's findings. The script has no single-reviewer mode, so re-running means running Phase 1 again (both reviewers). When both failed there is nothing to continue with: ask whether to re-run or stop
   - Wait for the answer. On "continue", go on with the reviewer that succeeded only, and say in the Phase 5 summary which reviewer did not review
3. Assess each finding as `pr-review-triage` does (read its "4.5 Evaluate and fix": findings are suggestions, checked against the actual code, validity measured rather than guessed)
4. Label each finding for the plan below (this command's own labels): ✅ adopted = valid and in line with the project policy; ⚠️ needs review = partly valid, needs adjustment; ❌ rejected = invalid, or against the architecture policy; a valid problem that existed before this change is not fixed here, only recorded as `pr-review-triage` 4.5 says

---

## Phase 3: Create Fix Plan

**Goal**: Plan the fixes to adopt

**Actions**:
1. Group the adopted and needs-review findings (by related file / feature)
2. Set the priority of the fixes:
   - 🔴 Critical: issues involving security / data integrity
   - 🟡 Important: functional issues / performance
   - 🟢 Nice-to-have: code quality / readability improvements
3. Create a fix plan file:
   - Path: `.context/workflow/plan/YYYYMMDDHHMMSS_fix_{summary_title}.md` (kept out of git by the exclude line the script added)
   - Contents:
     - List of files to fix
     - Details and reasons for each fix
     - Rejected findings and why
     - Implementation order

---

## Phase 4: Execute Fixes

**Goal**: Implement the fixes according to the plan

**Actions**:
1. Read the fix plan file
2. Make the fixes in priority order
3. Follow the conventions in the project's CLAUDE.md
4. Run related tests, if any, to confirm

---

## Phase 5: Summary

**Goal**: Report completion and update documents

**Actions**:
1. Write a summary of the fixes made:
   - List of files fixed
   - Adopted findings and how they were addressed
   - Rejected findings and why
2. Append the results to the fix plan file
3. Propose feedback to CLAUDE.md if needed

---

## Notes

- Fix plans are saved in `.context/workflow/plan/`
- Ask the user when unsure
- Reject findings that go against the architecture policy, stating the reason
