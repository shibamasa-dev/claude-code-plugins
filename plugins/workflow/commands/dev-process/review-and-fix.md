---
description: Workflow that runs AI review -> evaluation -> fix plan -> implementation end to end
argument-hint: Optional review scope description
---

# Review and Fix Workflow

A workflow that runs AI reviews with multiple agents, evaluates the results, and makes the appropriate fixes.

## Core Principles

- **Always check the codebase**: reviews can raise narrowly scoped points or points that go against the architecture strategy, so always check the related code before deciding
- **Follow CLAUDE.md**: the project's architecture policy and coding conventions come first
- **Choose sensibly**: don't take every finding at face value; judge its validity in the project's context

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
     - `dangerouslyDisableSandbox: true` (the codex CLI writes its session state under `~/.codex`, which is outside the sandbox's write allowlist; alternatively the user can allow `~/.codex` via `/sandbox` and then this is not needed)
2. The review script notifies its messages asynchronously, so end for now without waiting for the script to finish.

---

## Phase 2: Evaluate Review Results

**Goal**: Read the review results and evaluate the validity of each finding

**Actions**:
1. Analyze the review results from the stdout output obtained in Phase 1
2. For each finding, check:
   - **Always read the related source code**
   - Consistency with the architecture policy in CLAUDE.md
   - Project-specific circumstances (code kept for future use, intentional design, etc.)
   - The technical validity of the finding
3. Classify the findings:
   - ✅ **Adopt**: a valid finding in line with the project policy
   - ⚠️ **Needs review**: partly valid but needs adjustment
   - ❌ **Reject**: goes against the architecture strategy, or ignores the context

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
