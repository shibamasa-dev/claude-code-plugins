---
name: style-guide
description: How to write test cases. Gherkin format, how to write steps, tags, forbidden words. Product-independent.
last_reviewed: 2026-10-04
review_after: 2027-04-04
status: active
---

# Test case style guide

A test case has exactly one pass condition: **someone other than the author can follow the steps and decide Pass / Fail on the spot.** Every rule below comes from that.

## Gherkin is the source; tables come later

Write cases in Gherkin first. When a list such as a spreadsheet is needed, convert it from the Gherkin. Starting from a table means no format constraints, so "works nicely"-style wording slips in and is hard to spot in review. Gherkin has a fixed shape, so the checking hook can reject it mechanically.

Write cases in the user's language. Step text in Japanese (or any other language) is fine; keep the Gherkin keywords (`Feature`, `Scenario`, `Given`, `When`, `Then`, ...) in English, because the checking hook looks for `Scenario`.

## Shape of one case

```gherkin
Feature: <feature name>

  @P1 @UI
  Scenario: <what you want to confirm, in one sentence>
    Given <precondition>
    When  <action>
    Then  <expected result>
```

- Put tags directly above `Scenario:` / `Scenario Outline:`. Tags above `Feature:` are inherited by every case under it, so you can no longer vary priority or execution method per case
- When you check the same flow repeatedly with different values, combine them into a `Scenario Outline` with `Examples`

```gherkin
  @P2 @API
  Scenario Outline: <what you want to confirm, in one sentence>
    Given <a precondition that includes <item>>
    When  <action>
    Then  <an expected result that includes <expected>>

    Examples:
      | item         | expected     |
      | <real value> | <real value> |
```

- Use every `Examples` column somewhere in the steps. An unused column leaves the reader unable to tell what differs between rows

## Writing steps

| Step | What to write | Form |
|---|---|---|
| Given | The state that holds before the action starts | "... is ...", "there is ..." |
| When | The action the tester performs. One action per step | "does ..." |
| Then | What can be observed as the result of the action | "... is displayed", "... becomes ..." |

Write Then with **real values whose truth is decided on the spot**. If the reader has to work out "what counts as passing", it is not written yet.

| Before | After |
|---|---|
| The list shows up fine | The list shows 3 rows with status "Pending", and the count field shows "3" |
| Saving works | "Saved" is displayed, and the entered address is still there after reloading |
| Nothing goes wrong | No error banner at the top of the screen, and the Submit button is clickable again |

---

## Tags

There are three kinds of tags. **Priority** and **execution method** are required, exactly one each, on every case; **automation** is added only when it applies. Execution method and automation are separate concerns, so do not use one to express both (a case checked via API and handled only by automated tests gets both).

### Priority (required, one)

| Tag | Guideline |
|---|---|
| `@P1` | If it breaks, the business stops. Amount and quantity calculations, login and permissions, whether data create/update/delete succeeds, whether the main screen transitions work |
| `@P2` | It hurts if it breaks, but there is a workaround. Misaligned display, search conditions and sort order, secondary input checks, error wording |
| `@P3` | The business continues even if it breaks. Visual polish, rare combinations, checks for future needs |

When unsure, ask: "Would we release with this case still failing?" If not, it is `@P1`.

**Cases that only record current behavior are treated separately.** For cases that pin down a known bug or behavior that runs without any spec, the question above does not work (failing means someone fixed it). Put "pins current behavior" in the Scenario name, and decide priority by "who would be hurt, and how much, if this behavior changed silently".

### Execution method (required, one)

Decide by **what a manual tester operates to start the case**, not by where the result is checked.

| Tag | When |
|---|---|
| `@UI` | It can be started from a screen. Anything testable from a screen goes here by default |
| `@API` | There is no entry point on a screen and it can only be started by sending a request directly. Conditions that cannot be created from a screen also go here |

Testable-from-a-screen cases lean to `@UI` because "the API returns the right value" and "the screen shows that value correctly" are separate checks. Passing on the API alone misses screen-side bugs.

If the target has no screen (backend API, batch, data integration, CLI), all cases may be `@API`.

### Automation (optional)

| Tag | When |
|---|---|
| `@AUTO` | Handled only by automated tests and excluded from manual testing |

The criterion is "is the effort to reproduce it by hand worth the confidence the case gives". Not whether it is literally impossible by hand.

- Add it for: responses when an external service is down, rare concurrent updates, expirations you would have to wait a long time for, conditions that require swapping internal state
- Do not add it for: things that are tedious to prepare but doable by hand (registering initial data, changing permissions)

When unsure, do not add it; write the reason under `## Points to confirm` in the output. Once excluded from manual testing, nobody checks it by eye from then on. Do not decide silently.

## Write in the words on the screen

The person who reads and runs the cases is often a manual tester who does not read code. API paths or internal constant names do not tell them where to touch on screen.

- Use the names shown on screen. For mapping internal names, see the project's `ui-terms.md` (internal term ↔ on-screen label)
- If the mapping is unknown, do not invent a name; leave it under `## Points to confirm`
- For targets without a screen, internal identifiers are natural. The checking hook only WARNs and does not block. When a WARN appears, state in the output whether you kept the term because there is no screen, or because you failed to look up the mapping

---

## Forbidden word definitions (machine-readable)

The checking hook reads the blocks below at run time. The forbidden words are not written in the hook so that there is a single definition. Change one line here and the hook's verdict changes from the next run.

Each line is matched as a case-sensitive substring of a line in the case file. Japanese words are kept for test cases written in Japanese.

### Vague words (BLOCK — must be rewritten if found)

<!-- lint:vague-words -->
- 正しく
- 適切に
- 問題なく
- きちんと
- 妥当に
- 正常に動作
- correctly
- appropriately
- properly
- without problems
- reasonably
- works normally
<!-- /lint:vague-words -->

### Internal term patterns (WARN — notify only, do not block)

Written as regular expressions. Keep them as WARN until the project has a UI-terms mapping. Blocking with nothing to check against stops work with no way to fix it.

<!-- lint:internal-term-patterns -->
- /api/
- \b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b
<!-- /lint:internal-term-patterns -->
