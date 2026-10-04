#!/bin/bash
# 並列レビュー実行スクリプト
# 複数Agentのレビューを同時実行して、両方完了したら結果を出力
# Usage: ./agent-review.sh [タイトル]

set -e

# ================================
# デバッグ設定
# ================================
DEBUG_MODE=true  # デバッグログを出力する場合は true
LOG_DIR="logs"
LOG_FILE="${LOG_DIR}/agent-review-$(date +%Y%m%d).log"

# ログディレクトリ作成
mkdir -p "$LOG_DIR"

# デバッグログ関数
debug_log() {
  if [ "$DEBUG_MODE" = true ]; then
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [DEBUG] $*" >> "$LOG_FILE"
  fi
}

# エラーログ関数
error_log() {
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$timestamp] [ERROR] $*" >> "$LOG_FILE"
  echo "[$timestamp] [ERROR] $*" >&2
}

debug_log "=========================================="
debug_log "スクリプト開始: $0"
debug_log "引数: $*"
debug_log "カレントディレクトリ: $(pwd)"
debug_log "=========================================="

mkdir -p .context/review

# タイムスタンプ
TIMESTAMP=$(date +%Y%m%d%H%M%S)
debug_log "タイムスタンプ: $TIMESTAMP"

# タイトル（引数があれば使用）
TITLE="$1"
if [ -n "$TITLE" ]; then
  SUFFIX="_${TITLE}"
  debug_log "タイトル指定あり: $TITLE"
else
  SUFFIX=""
  debug_log "タイトル指定なし"
fi

CODEX_FILE=".context/review/${TIMESTAMP}_review${SUFFIX}_by_codex.md"
CODERABBIT_FILE=".context/review/${TIMESTAMP}_review${SUFFIX}_by_coderabbit.md"
debug_log "Codex出力ファイル: $CODEX_FILE"
debug_log "CodeRabbit出力ファイル: $CODERABBIT_FILE"

# Codex レビュー（バックグラウンド実行）
debug_log "Codexレビュー開始..."
debug_log "Codexコマンド: codex exec '/review 日本語で出力してください。' --output-last-message $CODEX_FILE"
codex exec '/review 日本語で出力してください。' --output-last-message "$CODEX_FILE" > /dev/null 2>&1 &
PID1=$!
debug_log "Codex PID: $PID1"

# CodeRabbit レビュー（バックグラウンド実行）
debug_log "CodeRabbitレビュー開始..."
debug_log "CodeRabbitコマンド: coderabbit --plain --type uncommitted > $CODERABBIT_FILE"
coderabbit --plain --type uncommitted > "$CODERABBIT_FILE" 2>&1 &
PID2=$!
debug_log "CodeRabbit PID: $PID2"

# 両方の完了を待つ（非0終了でもスクリプトを継続）
debug_log "両プロセスの完了待ち開始 (PID: $PID1, $PID2)"
set +e
wait $PID1
CODEX_EXIT=$?
set -e
debug_log "Codex終了コード: $CODEX_EXIT"

set +e
wait $PID2
CODERABBIT_EXIT=$?
set -e
debug_log "CodeRabbit終了コード: $CODERABBIT_EXIT"

# ファイル存在確認（存在しない場合は早期終了）
HAS_ERROR=false
if [ -f "$CODEX_FILE" ]; then
  debug_log "Codexファイル存在: OK ($(wc -c < "$CODEX_FILE") bytes)"
else
  error_log "Codexファイルが存在しません: $CODEX_FILE (終了コード: $CODEX_EXIT)"
  HAS_ERROR=true
fi

if [ -f "$CODERABBIT_FILE" ]; then
  debug_log "CodeRabbitファイル存在: OK ($(wc -c < "$CODERABBIT_FILE") bytes)"
else
  error_log "CodeRabbitファイルが存在しません: $CODERABBIT_FILE (終了コード: $CODERABBIT_EXIT)"
  HAS_ERROR=true
fi

if [ "$HAS_ERROR" = true ]; then
  error_log "レビューファイルの生成に失敗しました"
  exit 1
fi

# 結果を出力
debug_log "結果出力開始"
echo "✅ 全てのレビューが完了しました！"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Codex Review"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat "$CODEX_FILE"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐰 CodeRabbit Review"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat "$CODERABBIT_FILE"

debug_log "スクリプト正常終了"
debug_log "=========================================="
