#!/usr/bin/env bash
# このリポジトリ固有のセッション層手順。setup.sh から source される(リモートでのみ実行)。
# 編集してよいのはこのファイルと environment-setup.sh。setup.sh は共通部(スキル再実行で上書き)。
#
# 重い導入(apt・重量パッケージ・グローバル CLI)はここに書かない —
# environment-setup.sh(環境層。claude.ai の Setup script に内容を貼る)へ。
#
# 必要なネットワークホスト(既定の Trusted allowlist 外のもの): なし
#   ※ ある場合はここに列挙し、claude.ai 環境の Network access を Custom にして追加する。

# セッションに必須の環境変数(未設定なら WARNING を出す。値は claude.ai の環境ダイアログで設定)
REQUIRED_ENV_VARS=()

# 毎セッション実行(SessionStart hook 経由)。冪等かつ数十秒以内に保つこと。
# ここに置くもの: リポジトリの状態に追従すべき軽い処理(依存同期・venv 作成など)。
light_steps() {
  :
  # 例(Node): cd "$REPO_ROOT" && npm ci --no-audit --no-fund
  # 例(Python): 環境層で system に入れた重量パッケージを --system-site-packages で見せる
  #   [ -x "$REPO_ROOT/.venv/bin/python" ] || python3 -m venv --system-site-packages "$REPO_ROOT/.venv"
  #   "$REPO_ROOT/.venv/bin/pip" install -q -e "$REPO_ROOT"
}

# 環境が使える状態かの軽量チェック(exit 0 = OK)。毎セッション走るので数秒以内に保つこと。
verify() {
  :
  # 例: "$REPO_ROOT"/.venv/bin/python -c "import build123d" 2>/dev/null
}
