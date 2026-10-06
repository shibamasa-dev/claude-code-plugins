#!/bin/bash
# このプラグインの hooks の回帰スイープ（tests/test-*.sh を全部回して集計する）。
#
# 使い方: bash tests/run-all.sh
# 期待どおりでない行だけ ❌ が付く。件数が合っていても ❌ が1件でもあれば止めて読むこと。
cd "$(dirname "$0")" || exit 1
for s in test-*.sh; do
  echo; echo "▼ $s"
  bash "$s" 2>&1
  # 途中で落ちたスクリプトを「食い違い 0 件」に紛れさせない（awk はパイプの終了コードを見ないため、判定行にして数える）
  rc=$?; [ "$rc" = 0 ] && r=ok || r=crashed
  # 幅指定（%-56s）はロケールによってはマルチバイト文字の途中で切れ、awk が読めなくなる（CI の macOS で実測）
  printf '  %s: exit %s -> %s (ok 期待)\n' "$s" "$rc" "$r"
done | awk '
  /^▼/ {print; next}
  /期待/ {
    got = ""; want = ""
    if (match($0, /-> *[a-z]+/)) { got = substr($0, RSTART, RLENGTH); sub(/-> */, "", got) }
    if (match($0, /\([a-z]+ 期待/)) { want = substr($0, RSTART + 1, RLENGTH - 1); sub(/ 期待/, "", want) }
    # 判定行（-> を含む）は、実際の値か期待値のどちらかが読めないだけでも食い違いに数える
    # （期待値が空のまま並ぶ・テストが途中で落ちて実際の値が欠ける、を素通りさせない）
    if (index($0, "->") && (got == "" || want == "" || got != want)) { bad++; print "❌" $0 }
    else { ok++; print "  " $0 }
    next }
  {print}
  END {printf "\n==== 期待どおり %d 件 / 食い違い %d 件 ====\n", ok, bad+0}'
