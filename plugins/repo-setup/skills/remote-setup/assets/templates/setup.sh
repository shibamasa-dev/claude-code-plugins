#!/usr/bin/env bash
# リモート実行環境(クラウド VM)専用のセッション層ランナー。
# remote-setup スキルが生成する共通部 — このファイルは手で編集しない(スキル再実行で上書きされる)。
# リポジトリ固有の手順は steps.sh、VM プロビジョニング(重い導入)は environment-setup.sh に書く。
#
# 起動経路: .claude/settings.json の SessionStart hook(毎セッション)。
# 手動リトライも可: bash scripts/remote-setup/setup.sh
set -u

# ---- リモート判定ゲート: ローカルでは何も出力せず即終了する ----
is_remote() {
  # 公式のクラウド環境フラグ(主判定。Anthropic 管理のリモートインフラでのみ true)
  [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && return 0
  # 非公式・実測値による副判定(remote_cowork / remote_desktop など)
  case "${CLAUDE_CODE_ENTRYPOINT:-}" in remote_*) return 0 ;; esac
  # 明示オーバーライド: Codex / Cursor 等のクラウドサンドボックスのアダプタは
  # (それ自体がクラウド専用の機構から)REMOTE_SETUP_FORCE=1 を付けて呼ぶ。
  # ローカルでの動作テストにも使えるが、実インストールが走る点に注意。
  [ "${REMOTE_SETUP_FORCE:-}" = "1" ] && return 0
  return 1
}
is_remote || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_NAME="$(basename "$REPO_ROOT")"

STATE_DIR="${HOME}/.cache/remote-setup"
mkdir -p "$STATE_DIR"
LOG_FILE="$STATE_DIR/${REPO_NAME}.log"
STAMP_FILE="$STATE_DIR/${REPO_NAME}.stamp"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >>"$LOG_FILE"; }
# stdout は SessionStart hook 経由でセッションの context に注入される — 短く保つ
say() { echo "[remote-setup] $*"; log "$*"; }

# shellcheck source=steps.sh
. "$SCRIPT_DIR/steps.sh"

steps_hash() { sha256sum "$SCRIPT_DIR/steps.sh" | cut -d' ' -f1; }

check_env_vars() {
  local v missing=()
  for v in ${REQUIRED_ENV_VARS[@]+"${REQUIRED_ENV_VARS[@]}"}; do
    [ -z "${!v:-}" ] && missing+=("$v")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    say "WARNING: 未設定の環境変数: ${missing[*]}(claude.ai の環境ダイアログで設定する)"
  fi
}

# 冪等 fast path: steps.sh 不変 + verify OK なら即終了
if [ -f "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE")" = "$(steps_hash)" ] \
   && verify >>"$LOG_FILE" 2>&1; then
  say "OK (cached)"
  check_env_vars
  exit 0
fi

say "セッション層セットアップ実行(light_steps)"
light_steps >>"$LOG_FILE" 2>&1 || say "ERROR: light_steps 失敗。ログ: $LOG_FILE"
if verify >>"$LOG_FILE" 2>&1; then
  steps_hash >"$STAMP_FILE"
  say "OK"
else
  say "WARNING: verify 失敗。環境層の導入漏れの可能性 — claude.ai 環境ダイアログの Setup script に scripts/remote-setup/environment-setup.sh の内容が貼られているか確認(貼り直すと環境キャッシュが再構築される)。ログ: $LOG_FILE"
fi
check_env_vars
# hook はセッションをブロックしない: 失敗も WARNING として context に伝えるのみ
exit 0
