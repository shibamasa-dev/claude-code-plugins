## What changes

<!-- What changes for users. Before / After is easiest to follow -->

## Related issue

<!-- Always fill in the next two lines (a convention of the workflow plugin's dev-flow skill)
     Closes #N (meets every acceptance criterion) or Refs #N (only some). For a request without an issue: Refs: none (verbal request)
     Arch-Review: not-needed — <reason>  or  Arch-Review: approved — <where the GO is> -->

Refs #
Arch-Review: not-needed — 

## Checked

- [ ] Bumped the `version` of every plugin whose contents changed, and added a heading for that version to `CHANGELOG.md`
- [ ] `claude plugin validate --strict` passes
- [ ] If a `README.md` changed, its `README.ja.md` says the same (and vice versa)
- [ ] If hooks changed, `plugins/<plugin>/tests/run-all.sh` passes
- [ ] No personal paths, email addresses or internal names (`python3 .github/scripts/check-repo.py`)
