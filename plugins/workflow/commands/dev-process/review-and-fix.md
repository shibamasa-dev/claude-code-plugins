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
   - Output files: `.context/review/{YYYYMMDDHHMMSS}_review[_{title}_by_{agent}].md`
   - **Important**: pass these parameters to the Bash tool
     - `run_in_background: true`
     - The codex CLI writes its session state under `~/.codex`, which is outside the sandbox's default write allowlist. Prefer having the user allow only `~/.codex` via `/sandbox`; pass `dangerouslyDisableSandbox: true` only when that limited allowance can't be used
2. The review script notifies its messages asynchronously, so end for now without waiting for the script to finish.

---

## Phase 2: Evaluate Review Results

**Goal**: Decide which findings to act on

**Actions**:
1. Read the review results from the output of Phase 1
2. Assess each finding as `pr-review-triage` does (read its "4.5 Evaluate and fix": findings are suggestions, checked against the actual code, validity measured rather than guessed)
3. Label each finding for the plan below (this command's own labels): ✅ adopted = valid and in line with the project policy; ⚠️ needs review = partly valid, needs adjustment; ❌ rejected = invalid, or against the architecture policy

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
   - Path: `.context/plan/YYYYMMDDHHMMSS_fix_{summary_title}.md`
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

- Fix plans are saved in `.context/plan/`
- Ask the user when unsure
- Reject findings that go against the architecture policy, stating the reason
