SIGNALS_PY="${SIGNALS_PY:-$HOME/dev/10_ACMECO/02_Project/ACMECO/TARO-BOT-CC/.claude/skills/signal-inbox/scripts/signals.py}"

# --no-worktree ガード: メインtreeに未コミット変更があれば拒否（finding #1719 事故防止）

gh stack merge 42 --yes          # PR #42 plus every unmerged PR below it

# worktree 行のパスは空白を含みうるので $2 でなく "worktree " prefix だけ外す。
