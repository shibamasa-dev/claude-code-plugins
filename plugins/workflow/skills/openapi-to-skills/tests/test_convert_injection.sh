#!/bin/bash
# convert.py が spec 由来の値を生成スクリプト（auth/*.sh）へ素で埋め込まないことの回帰。
# 背景: securitySchemes のキー名や tokenUrl に "…" や $(…) を仕込んだ spec から生成した
#       setup.sh / token-manager.sh を実行すると任意コマンドが走った（spec は URL からも読める）。
#
# 使い方: bash tests/test_convert_injection.sh   （uv が必要）
# 期待どおりでない行だけ ❌ が付く。
set -u
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d /tmp/openapi-injection-test.XXXX)
trap 'rm -rf "$T"' EXIT
bad=0

conv() { uv run -q --project "$SKILL_DIR" "$SKILL_DIR/scripts/convert.py" "$@" >/dev/null 2>&1 && echo ok || echo refuse; }
row() {
  [ "$2" = "$3" ] && m="  " || { m="❌"; bad=$((bad + 1)); }
  printf '%s %-56s -> %-6s (%s 期待)\n' "$m" "$1" "$2" "$3"
}

# --- 悪意ある spec（キー名・tokenUrl それぞれ単独で） ---
cat > "$T/evil-name.yaml" <<YAML
openapi: 3.0.3
info: {title: Evil, version: "1"}
paths: {}
components:
  securitySchemes:
    'k"; touch $T/PWNED; echo "':
      type: apiKey
      in: header
      name: X
YAML
cat > "$T/evil-url.yaml" <<YAML
openapi: 3.0.3
info: {title: Evil, version: "1"}
paths: {}
components:
  securitySchemes:
    cc:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: 'https://x/\$(touch $T/PWNED)'
          scopes: {}
YAML

# --- 無害な spec（説明文にだけ特殊文字がある。実行されない欄なので変換できること） ---
cat > "$T/benign.yaml" <<'YAML'
openapi: 3.0.3
info:
  title: Pet Store API
  version: 1.0.0
  description: "Descriptions may contain $(x) `y` ; | & < > freely."
paths:
  /pets:
    get:
      operationId: listPets
      tags: [pets]
      responses:
        "200": {description: OK}
components:
  securitySchemes:
    oauth_cc:
      type: oauth2
      description: "see `docs` $(not run)"
      flows:
        clientCredentials:
          tokenUrl: https://auth.example.com/token
          scopes: {read: Read access}
    api_key:
      type: apiKey
      in: header
      name: X-API-Key
YAML

echo '=== 悪意ある spec は変換を止める ==='
row 'キー名に引用符・; を含む spec を拒否する' "$(conv "$T/evil-name.yaml" -o "$T/out-name")" refuse
row 'tokenUrl に $( ) を含む spec を拒否する' "$(conv "$T/evil-url.yaml" -o "$T/out-url")" refuse
row '拒否したときファイルを生成しない' "$([ -e "$T/out-name" ] || [ -e "$T/out-url" ] && echo files || echo none)" none

echo '=== 検証をすり抜けた値もテンプレート側で引用される（二重の防御） ==='
# 検証を通さずテンプレートを直接描画し、生成された resolve_token_url だけを実行する
uv run -q --project "$SKILL_DIR" python - "$SKILL_DIR/scripts" "$T" <<'PY' >"$T/tm.sh" 2>/dev/null
import sys
sys.path.insert(0, sys.argv[1])
from convert import create_renderer
url = f"https://x/$(touch {sys.argv[2]}/PWNED)"
print(create_renderer().get_template("token-manager.sh.j2").render(
    skill_name="x", schemes=[{"name": "cc", "token_url": url, "openid_connect_url": None}]))
PY
bash -c "$(sed -n '/^resolve_token_url()/,/^}/p' "$T/tm.sh"); SCHEME=cc; resolve_token_url" >/dev/null 2>&1
row 'tokenUrl の $( ) が実行されない' "$([ -e "$T/PWNED" ] && echo pwned || echo clean)" clean

echo '=== 無害な spec は従来どおり生成する ==='
row '説明文に特殊文字があっても変換できる' "$(conv "$T/benign.yaml" -o "$T/out-ok")" ok
row '生成した setup.sh が bash -n を通る' "$(bash -n "$T/out-ok/pet-store-api/auth/setup.sh" 2>/dev/null && echo ok || echo ng)" ok
row '生成した token-manager.sh が bash -n を通る' "$(bash -n "$T/out-ok/pet-store-api/auth/token-manager.sh" 2>/dev/null && echo ok || echo ng)" ok
row '-n の名前もファイル名用に無害化される' "$(conv "$T/benign.yaml" -o "$T/out-n" -n 'a"b c' >/dev/null; [ -d "$T/out-n/a-b-c" ] && echo ok || echo ng)" ok

printf '\n==== 食い違い %d 件 ====\n' "$bad"
[ "$bad" = 0 ]
