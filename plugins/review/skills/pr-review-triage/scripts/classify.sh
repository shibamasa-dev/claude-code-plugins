#!/bin/bash
# PR の差分を light / heavy に振り分ける判定本体（gh も git も呼ばない。同じ入力なら同じ出力）。
# 使い方: classify.sh [<numstat ファイル>]   （省略時は stdin）
#   入力: `git diff --numstat` 形式の行 <追加>\t<削除>\t<パス>（PR からは手元で `git diff --numstat origin/<base>...HEAD`）
#   出力: 1 行目に light か heavy、2 行目以降に「- 」で始まる理由
# 基準と閾値の根拠は SKILL.md。迷ったら heavy に倒す（見逃しの方が bot 1 回分より高くつく）
set -u
MAX_LINES=200

awk -F'\t' -v max="$MAX_LINES" '
function base(p,  n, a) { n = split(p, a, "/"); return a[n] }
function list(arr, n,  s, i) {
  s = arr[1]; for (i = 2; i <= n && i <= 5; i++) s = s ", " arr[i]
  if (n > 5) s = s " ほか " (n - 5) " 件"
  return s
}
NF >= 3 {
  path = $3
  # git の rename 表記（dir/{a => b}.md・a => b）は新しい名前で見る
  if (path ~ / => /) { gsub(/[{][^}]* => /, "", path); gsub(/[}]/, "", path); sub(/.* => /, "", path) }
  files++
  if ($1 == "-" || $2 == "-") bin[++nbin] = path   # バイナリは行数が出ない
  else total += $1 + $2
  b = tolower(base(path))
  if (b !~ /\.(md|markdown|txt|rst|adoc)$/) nondoc[++nnon] = path
  else if (b == "skill.md" || b == "claude.md" || b == "agents.md") named[++nnam] = path
  else if (("/" path) ~ /\/(skills|hooks|agents|commands|rules|\.github)\//) behav[++nbeh] = path
}
END {
  r = ""
  if (files == 0) r = r "- 差分が空（取得に失敗した可能性がある）\n"
  if (nnon) r = r "- 文章以外のファイル: " list(nondoc, nnon) "\n"
  if (nbin) r = r "- バイナリ: " list(bin, nbin) "\n"
  if (nnam) r = r "- 振る舞いを決める文書（ファイル名）: " list(named, nnam) "\n"
  if (nbeh) r = r "- 振る舞いを決めるパス配下の文書: " list(behav, nbeh) "\n"
  if (total > max) r = r "- 変更行数 " total " 行 > " max " 行\n"
  if (r != "") printf "heavy\n%s", r
  else printf "light\n- 文書のみ %d ファイル・%d 行\n", files, total
}
' "${1:-/dev/stdin}"
