#!/bin/bash
# Copy the pre-commit hook and the check script into this repo's .git/hooks/ and enable them.
# - Never run working-tree files directly, so code from a checked-out branch (including external PRs) doesn't run locally.
#   The copy source is origin/main (reviewed and merged), not the working tree.
#   This script itself runs from the working tree, so check out main and review it before running
# - Never delete existing hooks:
#   - Hooks elsewhere (a global core.hooksPath, etc.) are not written to; their location is recorded and they are called afterwards
#   - Another pre-commit already in .git/hooks is moved to pre-commit.prior and called afterwards
#   - Reinstalling keeps the recorded location
set -eu
cd "$(git rev-parse --show-toplevel)"
gitdir="$(cd "$(git rev-parse --git-common-dir)" && pwd -P)"
mkdir -p "$gitdir/hooks"
dest="$(cd "$gitdir/hooks" && pwd -P)"
# If .git/hooks is a symlink to a shared directory, we would rewrite other repos' hooks too
[ "$dest" = "$gitdir/hooks" ] || { echo "install.sh: .git/hooks points elsewhere ($dest); not installing" >&2; exit 1; }
MARK="claude-code-plugins:pre-commit"

# Resolve the earlier hooks location to an absolute path and compare with $dest (a relative path or ~ to the same place is ourselves)
prior=$(git config core.hooksPath || true)
case "$prior" in
  "~/"*) prior="$HOME/${prior#\~/}" ;;
esac
if [ -n "$prior" ] && [ -d "$prior" ]; then
  prior=$(cd "$prior" && pwd -P)
else
  prior=""
fi
if [ "$prior" = "$dest" ]; then
  prior=$(cat "$dest/prior-hooks-path" 2>/dev/null || true)  # reinstall: keep the location recorded last time
fi
case "$prior" in "$(pwd -P)/.githooks") prior="" ;; esac  # don't carry over the old setup (pointing straight at the working tree)

git fetch -q origin main
# If extraction fails, install nothing (so an empty hook doesn't silently drop the earlier checks)
tmp=$(mktemp -d)
git show origin/main:.githooks/pre-commit > "$tmp/pre-commit"
git show origin/main:.github/scripts/check-repo.py > "$tmp/check-repo.py"

# Move another pre-commit in .git/hooks aside and call it afterwards (our own previous one can be overwritten)
if [ -e "$dest/pre-commit" ] && ! grep -q "$MARK" "$dest/pre-commit"; then
  if [ -e "$dest/pre-commit.prior" ]; then
    echo "install.sh: another pre-commit exists and pre-commit.prior is already taken; not overwriting (decide which to keep, then rerun)" >&2
    rm -r "$tmp"; exit 1
  fi
  mv "$dest/pre-commit" "$dest/pre-commit.prior"
fi
install -m 755 "$tmp/pre-commit" "$dest/pre-commit"
install -m 644 "$tmp/check-repo.py" "$dest/check-repo.py"
rm -r "$tmp"

if [ -n "$prior" ]; then
  printf '%s\n' "$prior" > "$dest/prior-hooks-path"
  # For earlier hooks other than pre-commit, add a thin entry point that just calls them (don't overwrite same-named hooks already in .git/hooks)
  for h in "$prior"/*; do
    n=$(basename "$h")
    [ -x "$h" ] && [ "$n" != pre-commit ] && [ ! -e "$dest/$n" ] || continue
    printf '#!/bin/sh\n# Entry point added by install.sh: calls the earlier hook (does nothing if it is gone)\n[ -x "%s" ] || exit 0\nexec "%s" "$@"\n' "$h" "$h" > "$dest/$n"
    chmod 755 "$dest/$n"
  done
else
  rm -f "$dest/prior-hooks-path"
fi
git config --local core.hooksPath "$dest"
echo "installed: $dest/pre-commit${prior:+ (also calls the earlier hooks in $prior)}$( [ -e "$dest/pre-commit.prior" ] && echo " (also calls the moved-aside $dest/pre-commit.prior)")"
