---
name: perspectives-common
description: The common layer of test perspectives that stays the same for every product. testcase-generator reads it before the project-specific perspectives.
last_reviewed: 2026-09-22
review_after: 2027-03-22
status: active
---

# Common test perspectives (product-independent)

This list holds only **perspectives that stay the same for every product**. Product-specific know-how such as "this feature tends to break here" goes in the project-specific layer described below.

## How to use — mark every perspective "In scope / Out of scope"

Do not skim the perspectives and pick only the ones that apply. **Mark every item In scope or Out of scope, and give each Out of scope item a one-line reason.**

Dropping one silently leaves no record that it was dropped. Whether you can later trace "why is this perspective missing" decides whether the test design can be re-read.

---

## 1. Input values

- [ ] **Valid values** — at least one per category or type. Do not let a single value represent all
- [ ] **Boundary values** — make **inside, exactly on, and outside** the boundary separate cases. Choose by value type:

| Value type | How to take the four points |
|---|---|
| Integers, counts | min-1 / min / max / max+1 |
| Enumerations, categories | outside the definition / first / last / (if any) undefined value |
| Continuous values (decimals, times, rates) | "-1 / +1" is undefined. Take two points on each side: **just outside the boundary / exactly on it**. **Show how far outside in the Examples values** |
| Clamping (rounded at both ends) | outside the lower bound / exactly the lower bound / exactly the upper bound / outside the upper bound. Write the **value after clamping** in Then |

When you reinterpret for continuous values, **write one line in the output saying how you did it**. Otherwise the next person designing the same function interprets it differently and the results diverge (which defeats the purpose of this list)
- [ ] **Invalid values** — wrong type / empty string / null / missing / special characters
- [ ] **Overflow and rounding** — input beyond the expected number of digits, handling of decimals

Why boundary values are not combined into one case: if the run fails, **you cannot tell which boundary failed**. Someone has to try again by hand to isolate it, which defeats the point of automating.

## 2. Numeric and monetary calculations

- [ ] If there are amount, quantity or rate calculations, turn them into cases **before any other perspective**
- [ ] **Pick values per branch of the formula** — rounding (up / down / half), tax or rate boundaries, conditions for discounts and surcharges
- [ ] If there is summing or proration across items, confirm the totals match

Do not stop at one random number. Wrong amounts **flow through while looking normal on screen**, so they are found late, and the later they are found the bigger the damage.

## 3. Preconditions and state

- [ ] When a precondition is not met, **which error state it falls into**
- [ ] Allowed / denied by permission or role
- [ ] Not logged in / session expired
- [ ] Running the same operation twice (idempotency, double registration)
- [ ] Target data with 0 / 1 / many records

## 4. Where to verify (UI or API)

- [ ] **Items that can be checked on screen are verified by operating the screen** (`@UI`)
- [ ] **Only conditions that cannot be reproduced on screen go to API checks** (`@API`)

"The API returns the expected value" and "that value is **displayed and controlled correctly on the screen the user sees**" are separate problems. Passing on API checks alone lets screen-side display and input-check bugs through.

**If the target has no screen, mark this perspective "Not applicable".** All cases being `@API` is not a sorting failure.

---

## 5. Self-check after generation (always run)

Inspect the whole set of generated test cases yourself against the items below. This is not external mechanical checking but **a self-check built into the generation procedure**.

There are four values to record. **Only NG requires a rewrite**; Not applicable and Deferred can be output as they are (but with a reason).

| Value | When to use |
|---|---|
| OK | It holds |
| NG | It does not hold → **rewrite before output** |
| Not applicable | The perspective structurally does not exist (UI items for a target with no screen, etc.) |
| Deferred | Cannot be settled without measuring (the actual exception message text, values that only appear at run time, etc.) |

Forcing it into two values (OK/NG) mixes in the lie of claiming a verdict on something that cannot be judged.

- [ ] **Are the case counts per perspective evenly lined up?** (e.g. five per perspective)
      Even counts are evidence of mechanical allocation that ignored the risk differences between perspectives. High-risk perspectives should get more cases
- [ ] **Are amount or numeric calculations checked with random values only?** (are the values per branch?)
- [ ] **Is anything passed on API checks alone, without a screen operation?**
      * **If the target has no screen (backend API, batch, ETL, CLI), mark this item "Not applicable".**
      Applying UI criteria to a target with no screen always fails structurally. Do not claim an item you cannot satisfy;
      write "Not applicable (the target has no screen)"
- [ ] Does every perspective marked Out of scope have a reason?
- [ ] Is every Then an observable real value? (see the style guide)

If you find a problem, do not stop at fixing it; **write a proposal in the output to add it to "Lessons from past failures" below**.
But **never edit this file directly** — this is global knowledge (shared by every project), so pouring in a finding from the one product
in front of you would affect other projects too. The user decides whether to add it.

---

## 6. Lessons from past failures

Keep adding the holes you fell into here. **This section growing is the evidence that this list is alive.**

When adding, include "when / which product / what was missed". Abstracted too far, it is useless the next time you read it.

<!-- Example:
- [ ] (2026-XX-XX / product name) When ..., check .... ... was missed and ... happened
-->

(none yet)

---

## 7. Project-specific perspectives (two-layer reference)

Everything above is the **common layer**. Product-specific know-how lives in each repo; **read the common layer first, then layer the specific one on top.**

Where the specific layer lives (**this definition is the single source. Both `testcase-generator` and `codebase-doctor`, which audits the project side, read it here and use the same locations**):

```
$CLAUDE_PROJECT_DIR/.claude/knowledge/perspectives.md   # project-specific test perspectives
$CLAUDE_PROJECT_DIR/.claude/knowledge/ui-terms.md       # internal term ⇔ on-screen label mapping
$CLAUDE_PROJECT_DIR/.claude/knowledge/playbook.md       # preconditions for running the tests
```

They go under `.claude/` so they sit with the project's agent settings (`settings.json`, project skills, hooks) and `codebase-doctor` can look after them together.

**You can design with the common layer alone even without the specific layer.** But when it is missing, state "No project-specific perspectives (designed from the common layer only)" in the output. Do not silently make having it and not having it look the same.
