`issue-writeback/fx-sess.json` was written by `hooks/issue-writeback.py` as it was before state moved to
`${CLAUDE_PLUGIN_DATA}` (a PostToolUse of `gh issue view 7 --repo example-org/example-repo`, session `fx-sess`, run
with HOME pointing at a temp directory). test-state-dir.sh copies it to the old `~/.claude/state/issue-writeback/`.
