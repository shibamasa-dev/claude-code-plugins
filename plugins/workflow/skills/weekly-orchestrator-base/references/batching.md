# How to bundle batches

The source is step 5(a) of the session-wrap skill (`${CLAUDE_PLUGIN_ROOT}/skills/session-wrap/SKILL.md`). If you change that one, change this one too.

## Principle

**Do not split too finely. Form batches by task size and dependencies.**
Making even small doc PRs one per item increases the number of parallel runs and the coordination effort.

Signs that items belong in the same batch (**any one** is enough):

- They touch the same set of files
- They use the same shared resource (the project skill holds the list of resources)
- One depends on the other (B uses A's result)
- Each is small (doc fixes, skill additions, and so on that fit in one PR)

Split only **things that are large, can proceed independently, and do not overlap in files or resources**.

**Send out at most 1–2 batches at a time.** Look at the results of the previous batch before sending the next.
There is one more reason not to add parallelism: too many parallel sessions can make connections unstable.

## What to write in the prompts when running in parallel

If they might compete for a shared resource, put both of the following into **both** prompts.
If only one prompt has them, the other side does not know the resource is shared.

1. **The turn-taking rule.** Take the lock with `mkdir` (it is created atomically, so there is no race):
   ```bash
   until mkdir /tmp/<project>-lock-<resource> 2>/dev/null; do sleep 30; done   # take
   # …work that uses the resource…
   rmdir /tmp/<project>-lock-<resource>                                         # release
   ```
   If the lock is not free for 30 minutes or more, do not keep waiting; send an interim report to the orchestrator and stop.
   If the project has per-resource lock rules (location, time limit), use those instead.
2. **Ownership ranges within the same file.** Write them at the level of file, section, or function, such as
   "Write only §3 of `docs/spec/xxx.md`. Do not touch §1 or §2."

## Items with a dependency

If B uses A's result, either put them in the same batch and write the order in the prompt, or send out B after A completes (after verifying its report).
Write `A → B` in the "Order" column of the plan section's batch table.
