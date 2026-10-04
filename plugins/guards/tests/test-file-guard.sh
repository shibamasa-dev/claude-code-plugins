#!/bin/bash
# file-guard.py の判定を全ケース記録する。「判定結果が変更前と完全に一致する」の証拠用。
# 引数で出力先を指定できるので、変更前/変更後を別ファイルに採って diff できる。
set -u
OUT="${1:-/dev/stdout}"

F=/tmp/fg-fixture
rm -rf "$F"
# skill レイアウト例外の2形（① パス要素に skills ② scripts/ の親に SKILL.md）
mkdir -p "$F/repo/docs/spec" "$F/repo/scripts/sub" \
         "$F/repo/skills/alpha/scripts" \
         "$F/repo/deliverables/beta/scripts"
: > "$F/repo/deliverables/beta/SKILL.md"
: > "$F/repo/docs/EXISTS.md"          # 既存ファイル上書きのケース用
: > "$F/repo/scripts/exists.sh"

# 仕様ファイル（FILE_GUARD_SPEC で渡す）。判定に要る guard ブロックだけを持つ最小版。
export FILE_GUARD_SPEC="$F/repo-structure.md"
cat > "$FILE_GUARD_SPEC" <<'SPEC'
<!-- guard:docs-allow-filenames -->
- README.md
<!-- /guard:docs-allow-filenames -->
<!-- guard:docs-subfolders -->
- spec: 何を・どう作る
- adr: なぜ
- research: 何がわかった
- ops: どう動かす
- reference: 何が正か
<!-- /guard:docs-subfolders -->
<!-- guard:script-extensions -->
- .sh
- .py
- .js
- .ts
- .mjs
- .rb
- .zsh
- .bash
<!-- /guard:script-extensions -->
<!-- guard:exemptions -->
- path-component-skills: パス要素のどこかが `skills` であるツリー全体
- sibling-skill-md: `scripts/` の親ディレクトリに `SKILL.md` がある場合
<!-- /guard:exemptions -->
SPEC
export HOOK="$(cd "$(dirname "$0")/.." && pwd)/hooks/file-guard.py"

probe() {
  python3 - "$1" <<'PY'
import json, subprocess, sys, os
p = subprocess.run(["python3", os.environ["HOOK"]],
    input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": sys.argv[1]}}),
    capture_output=True, text=True)
o = p.stdout.strip()
print("allow" if not o else json.loads(o).get("hookSpecificOutput", {}).get("permissionDecision", "allow"))
PY
}

{
  echo "# file-guard.py 判定記録"
  while IFS='|' read -r path label; do
    [ -z "$path" ] && continue
    printf '%-8s %s\n' "$(probe "$F/repo/$path")" "$label"
  done <<'CASES'
docs/foo.md|docs/ 直下の新規 .md
docs/README.md|docs/README.md（唯一の例外）
docs/readme.md|docs/readme.md（小文字・例外ではない）
docs/EXISTS.md|docs/ 直下だが既存ファイル（規約対象外）
docs/spec/foo.md|docs/spec/ 配下
docs/foo.txt|docs/ 直下だが .md でない
scripts/foo.sh|scripts/ 直下の新規スクリプト(.sh)
scripts/foo.py|scripts/ 直下の新規スクリプト(.py)
scripts/foo.ts|scripts/ 直下の新規スクリプト(.ts)
scripts/foo.txt|scripts/ 直下だがスクリプト拡張子でない
scripts/exists.sh|scripts/ 直下だが既存ファイル（規約対象外）
scripts/sub/foo.sh|scripts/sub/ 配下
skills/alpha/scripts/foo.sh|skill 例外① パス要素に skills
deliverables/beta/scripts/foo.sh|skill 例外② scripts/ の親に SKILL.md
deliverables/gamma/scripts/foo.sh|例外に当たらない scripts/ 直下
src/foo.sh|docs/ でも scripts/ でもない
CASES
} > "$OUT"
rm -rf "$F"
