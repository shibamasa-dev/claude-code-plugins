#!/usr/bin/env bash
# list-projects.sh - git リポジトリを番号付きで列挙
# Usage: list-projects.sh [root_dir]
# 既定 root: ~/dev
set -euo pipefail

root="${1:-$HOME/dev}"

if [ ! -d "$root" ]; then
  echo "ERROR: '$root' はディレクトリではありません" >&2
  exit 1
fi

# .git ディレクトリを探し、親ディレクトリ（リポジトリのルート）を列挙
repos_file=$(mktemp "${TMPDIR:-/tmp}/list-projects.XXXXXX")
find "$root" -maxdepth 4 -name .git -type d 2>/dev/null | sed 's|/\.git$||' | sort > "$repos_file"

count=$(wc -l < "$repos_file" | tr -d ' ')

if [ "$count" -eq 0 ]; then
  echo "リポジトリが見つかりませんでした: ${root}"
  rm -f "$repos_file"
  exit 0
fi

echo "プロジェクト一覧 (root: ${root})"
echo "---"
i=1
while IFS= read -r repo; do
  printf "%3d. %s\n" "$i" "$repo"
  i=$((i + 1))
done < "$repos_file"
rm -f "$repos_file"
echo "---"
echo "合計: ${count} 件"
