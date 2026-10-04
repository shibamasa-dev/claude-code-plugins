#!/bin/bash
# handoff.py の複数件化（2026-09-25）の回帰。並行セッションが互いの入口を上書きで消さないこと。
# 背景: 1 プロジェクト 1 件の上書きだったため、後から閉じたセッションが
#       別セッションの引き継ぎを黙って消した。
set -u
H="$(cd "$(dirname "$0")/.." && pwd)/hooks/handoff.py"
export HANDOFF_STATE_DIR=$(mktemp -d /tmp/handoff-test-state.XXXX)
REPO=$(mktemp -d /tmp/handoff-test-repo.XXXX)
(cd "$REPO" && git init -q . && git remote add origin git@github.com:example-org/handoff-test.git)

cnt() { python3 - "$HANDOFF_STATE_DIR" <<'PY'
import glob, json, sys
fs = glob.glob(sys.argv[1] + "/*.json")
n = len(json.load(open(fs[0]))["items"]) if fs else 0
print({0: "zero", 1: "one", 2: "two"}.get(n, "many"))
PY
}
rc() { (cd "$REPO" && python3 "$H" "$@" >/dev/null 2>&1) && echo ok || echo refuse; }
row() { printf '  %-52s -> %-5s (%s 期待)\n' "$1" "$2" "$3"; }

echo '=== 追記・更新 ==='
rc write --entry example-org/handoff-test#1 --state s1 --next n1 >/dev/null
row 'A を書く' "$(cnt)" one
rc write --entry example-org/handoff-test#2 --state s2 --next n2 >/dev/null
row '別の入口 B を書く（追記される）' "$(cnt)" two
rc write --entry example-org/handoff-test#1 --state s1b --next n1b >/dev/null
row '同じ入口 A を書き直す（件数は増えない）' "$(cnt)" two
got=$(cd "$REPO" && python3 "$H" show | grep -q 's1b' && ! (cd "$REPO" && python3 "$H" show | grep -q '状態: s1$') && echo ok || echo bad)
row 'A の中身が新しい値に置き換わる' "$got" ok

echo '=== SessionStart で全件注入 ==='
got=$(printf '{"hook_event_name":"SessionStart","source":"startup","cwd":"%s"}' "$REPO" | python3 "$H" \
      | grep -c 'handoff-test#' | awk '{print ($1==2)?"two":"bad"}')
row 'startup で 2 件とも出る' "$got" two

echo '=== consume ==='
row '複数あるとき --entry 無しの consume は拒否' "$(rc consume)" refuse
row '無い入口の consume は拒否' "$(rc consume --entry example-org/handoff-test#9)" refuse
rc consume --entry example-org/handoff-test#1 >/dev/null
row 'consume --entry A で A だけ消える' "$(cnt)" one
row '1 件だけなら --entry 無しで consume できる' "$(rc consume)" ok
row '最後の 1 件を消すとファイルも消える' "$(cnt)" zero

echo '=== 別リポの入口 ==='
row '別リポの入口は書かない' "$(rc write --entry example-org/other#1 --state s --next n)" refuse
row '--force なら書ける' "$(rc write --entry example-org/other#1 --state s --next n --force)" ok

rm -rf "$HANDOFF_STATE_DIR" "$REPO"
