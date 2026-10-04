#!/bin/bash
# pre-commit と検査スクリプトをこのリポの .git/hooks/ にコピーして有効にする。
# - 作業ツリーのファイルを直接実行しない: checkout したブランチ（外部の PR を含む）のコードが手元で走らないように。
#   コピー元も作業ツリーではなく origin/main（レビュー済みでマージされたもの）にする。
#   このスクリプト自体は作業ツリーから実行されるので、main を checkout した状態で中身を確認してから実行する
# - 既にあるフックは消さない:
#   - 別の場所のフック（グローバルの core.hooksPath 等）には書き込まず、場所を記録して続けて呼ぶ
#   - .git/hooks に既にある別の pre-commit は pre-commit.prior に退避して続けて呼ぶ
#   - 再インストールでも記録した場所を引き継ぐ
set -eu
cd "$(git rev-parse --show-toplevel)"
gitdir="$(cd "$(git rev-parse --git-common-dir)" && pwd -P)"
mkdir -p "$gitdir/hooks"
dest="$(cd "$gitdir/hooks" && pwd -P)"
# .git/hooks が共有ディレクトリへの symlink だと、他のリポのフックまで書き換えてしまう
[ "$dest" = "$gitdir/hooks" ] || { echo "install.sh: .git/hooks が別の場所（$dest）を指しているので入れない" >&2; exit 1; }
MARK="claude-code-plugins:pre-commit"

# 以前のフックの場所を、絶対パスに直して $dest と比べる（相対指定や ~ も同じ場所なら自分自身）
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
  prior=$(cat "$dest/prior-hooks-path" 2>/dev/null || true)  # 再インストール: 前回記録した場所を引き継ぐ
fi
case "$prior" in "$(pwd -P)/.githooks") prior="" ;; esac  # 以前の手順（作業ツリー直指し）は引き継がない

git fetch -q origin main
# 取り出しに失敗したら何も置かない（空のフックで以前の検査が黙って外れないように）
tmp=$(mktemp -d)
git show origin/main:.githooks/pre-commit > "$tmp/pre-commit"
git show origin/main:.github/scripts/check-repo.py > "$tmp/check-repo.py"

# .git/hooks に別の pre-commit があれば退避して続けて呼ぶ（自分の前回のものは上書きでよい）
if [ -e "$dest/pre-commit" ] && ! grep -q "$MARK" "$dest/pre-commit"; then
  if [ -e "$dest/pre-commit.prior" ]; then
    echo "install.sh: 別の pre-commit があり、退避先の pre-commit.prior も埋まっているので上書きしない（どちらを残すか決めてから再実行）" >&2
    rm -r "$tmp"; exit 1
  fi
  mv "$dest/pre-commit" "$dest/pre-commit.prior"
fi
install -m 755 "$tmp/pre-commit" "$dest/pre-commit"
install -m 644 "$tmp/check-repo.py" "$dest/check-repo.py"
rm -r "$tmp"

if [ -n "$prior" ]; then
  printf '%s\n' "$prior" > "$dest/prior-hooks-path"
  # pre-commit 以外の以前のフックは、そのまま呼ぶだけの薄い入口を置く（既存の .git/hooks の同名は上書きしない）
  for h in "$prior"/*; do
    n=$(basename "$h")
    [ -x "$h" ] && [ "$n" != pre-commit ] && [ ! -e "$dest/$n" ] || continue
    printf '#!/bin/sh\n# install.sh が置いた入口: 以前のフックを呼ぶ（消えていたら何もしない）\n[ -x "%s" ] || exit 0\nexec "%s" "$@"\n' "$h" "$h" > "$dest/$n"
    chmod 755 "$dest/$n"
  done
else
  rm -f "$dest/prior-hooks-path"
fi
git config --local core.hooksPath "$dest"
echo "installed: $dest/pre-commit${prior:+ (以前のフック $prior も続けて呼ぶ)}$( [ -e "$dest/pre-commit.prior" ] && echo " (退避した $dest/pre-commit.prior も続けて呼ぶ)")"
