#!/usr/bin/env bash
# spawn.sh - スピンオフセッション起動（tmux 上の独立した Claude Code セッション）
# Usage: spawn.sh [--worktree|--no-worktree] [--base <branch>] [--wait|--unattended] [--issue <ref>] [--model <name>] [--force-shared] <project_path> "<task>"
#   --worktree      (既定) base(既定 main)から spin/<slug> worktree を切り、そこで起動
#   --no-worktree   project_path でそのまま起動（読み取り専用タスク用）
#                   ※メインtreeに未コミット変更がある場合は拒否（--force-shared で強行）
#   --base <branch> worktree の土台ブランチ（既定: main）
#   --wait          待機モード。起動直後は着手せず概要を表示して停止し、ユーザーの「開始」指示で着手
#                   （--issue 無しの既定）
#   --unattended    投げっぱなしモード。起動直後にタスクへ即着手する（--issue 指定時の既定）
#   --issue <ref>   対応する GitHub issue（URL または owner/repo#N）。既定モードが unattended になる
#   --model <name>  Claude のモデル。省略時は Claude Code の既定に任せる
#   --force-shared  --no-worktree で未コミット変更があっても強行（非推奨）
#
# 差し込み口（環境変数。どちらも任意・失敗しても起動は続ける）:
#   SPINOFF_SEED_APPENDIX_CMD  標準出力をタスク文の末尾に足すコマンド（報告経路など、使う人ごとの指示を足す）
#   SPINOFF_POST_SPAWN_CMD     tmux 起動後に走らせるコマンド（追跡台帳への登録など）
#   どちらにも SPINOFF_SESSION / SPINOFF_PROJECT / SPINOFF_RUN_DIR / SPINOFF_BRANCH / SPINOFF_ISSUE を渡す。
#
# 対応 OS: macOS / Linux（tmux が必要。Windows は非対応）
set -euo pipefail

if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux が見つかりません。spinoff-session は tmux を使うため macOS / Linux 専用です（Windows は非対応）。" >&2
  exit 1
fi

use_worktree=1
base_branch="main"
wait_mode=1
explicit_wait=0
issue_ref=""
force_shared=0
model=""

while [ $# -gt 0 ]; do
  case "$1" in
    --worktree)     use_worktree=1; shift ;;
    --no-worktree)  use_worktree=0; shift ;;
    --base)         base_branch="${2:?--base にブランチ名が必要}"; shift 2 ;;
    --wait)         wait_mode=1; explicit_wait=1; shift ;;
    --unattended)   wait_mode=0; shift ;;
    --issue)        issue_ref="${2:?--issue に issue URL か owner/repo#N が必要}"; shift 2 ;;
    --model)        model="${2:?--model にモデル名が必要}"; shift 2 ;;
    --force-shared) force_shared=1; shift ;;
    --)             shift; break ;;
    -*)             echo "ERROR: unknown option $1" >&2; exit 1 ;;
    *)              break ;;
  esac
done

# --issue 指定時は unattended が既定（--wait 明示があればそちら優先）
if [ -n "$issue_ref" ] && [ "$explicit_wait" -eq 0 ]; then
  wait_mode=0
fi

# issue 参照の正規化: URL / owner/repo#N の両対応
issue_id=""
if [ -n "$issue_ref" ]; then
  if [[ "$issue_ref" =~ ^https://github\.com/([^/]+)/([^/]+)/issues/([0-9]+)/?$ ]]; then
    issue_id="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}#${BASH_REMATCH[3]}"
  elif [[ "$issue_ref" =~ ^([^/#[:space:]]+)/([^/#[:space:]]+)#([0-9]+)$ ]]; then
    issue_id="$issue_ref"
  else
    echo "ERROR: --issue は issue URL か owner/repo#N 形式で指定してください: $issue_ref" >&2
    exit 1
  fi
fi

if [ $# -lt 2 ]; then
  echo "Usage: spawn.sh [--worktree|--no-worktree] [--base <branch>] <project_path> \"<task>\"" >&2
  exit 1
fi

project_path="$1"
task="$2"

if [ ! -d "$project_path" ]; then
  echo "ERROR: '$project_path' はディレクトリではありません" >&2
  exit 1
fi

# どの repo で無人作業するかを必ず1行残す（bypassPermissions で動くので、起動元が一目で訂正できるように）
echo "📍 cwd宣言: ${project_path}"

timestamp=$(date +%Y%m%d-%H%M%S)
if [ -n "$issue_id" ]; then
  slug="issue-${issue_id##*#}-${timestamp}"
else
  task_part=$(printf '%s' "$task" | head -c 32 | LC_ALL=C tr -cs 'a-zA-Z0-9' '-' | LC_ALL=C tr '[:upper:]' '[:lower:]' | sed 's/^-//;s/-$//')
  slug="${task_part:+${task_part}-}${timestamp}"
fi
session="spin_${slug}"

run_dir="$project_path"
wt_line=""
branch=""
if [ "$use_worktree" -eq 0 ] && [ "$force_shared" -eq 0 ]; then
  if git -C "$project_path" rev-parse --show-toplevel >/dev/null 2>&1; then
    if [ -n "$(git -C "$project_path" status --porcelain 2>/dev/null)" ]; then
      echo "ERROR: '$project_path' に未コミット変更があります。--no-worktree の並行セッションは未コミット変更を壊し得ます。" >&2
      echo "       編集を伴うなら --worktree（既定）を使うか、読み取り専用と確信があれば --force-shared で強行してください。" >&2
      exit 1
    fi
  fi
fi
if [ "$use_worktree" -eq 1 ]; then
  if ! repo_root=$(git -C "$project_path" rev-parse --show-toplevel 2>/dev/null); then
    echo "ERROR: '$project_path' は git リポジトリではありません（--worktree 不可。読み取り専用なら --no-worktree）" >&2
    exit 1
  fi
  if ! git -C "$repo_root" rev-parse --verify --quiet "$base_branch" >/dev/null; then
    echo "ERROR: base ブランチ '$base_branch' が見つかりません" >&2
    exit 1
  fi
  repo_name=$(basename "$repo_root")
  wt_dir="${SPINOFF_WORKTREE_ROOT:-$HOME/.worktrees}/${repo_name}-${slug}"
  branch="spin/${slug}"
  echo "worktree 作成: $wt_dir (branch: $branch, base: $base_branch)"
  git -C "$repo_root" worktree add "$wt_dir" -b "$branch" "$base_branch"
  run_dir="$wt_dir"
  wt_line="  worktree     : ${wt_dir}
  ブランチ     : ${branch} (base: ${base_branch})"
fi

export SPINOFF_SESSION="$session" SPINOFF_PROJECT="$project_path" SPINOFF_RUN_DIR="$run_dir" \
       SPINOFF_BRANCH="$branch" SPINOFF_ISSUE="$issue_id"

run_task="$task"
if [ "$wait_mode" -eq 1 ]; then
  run_task="【待機タスク・起動直後は着手禁止】
このセッションには下記タスクが割り当てられているが、まだ実装・ファイル編集・git 操作・コマンド実行を一切してはならない。
起動直後にやること: タスク名と目的を3行以内で要約表示し、続けて「待機中です。『開始』と言われたら着手します。前提（対象ブランチ/ファイル/受入基準）の確認から始めます」とだけ伝えて停止する（質問も投げかけない・出力後に手を止める）。
以降、ユーザーが『開始』等の指示を出すまで待機する。開始を指示されたら、まずスコープと受入基準を対話で確認してからタスクを進めること。

━━━━━━ タスク本文 ━━━━━━
${task}"
fi

if [ -n "$issue_id" ]; then
  run_task="${run_task}

━━━━━━ issue対応スコープ（PR作成まで・マージしない）━━━━━━
対象 GitHub issue: ${issue_id}
次の順で進め、マージ・デプロイは起動元の明示指示が無い限りしない:
1. 実装→コミット→PR作成。PR 本文には 'Closes ${issue_id}' か 'Refs ${issue_id}' を書く
   （受け入れ基準が全項目 ✅ かつ issue body に '## 結果' を書き終えたときだけ Closes。それ以外は Refs＋未達項目と残件の行き先）。
   PR 本文の受け入れ基準表は issue 本文の基準を逐語で使う（言い換え・要約・別の基準への差し替えをしない）。達成していない行は ❌ にする。
2. PR を作成したら完了報告を出し、そのまま待機する（'/exit' しない。畳むのは起動元）。
   レビュー bot の到着を自分から待たない・ポーリングしない（pr-review-wait skill も使わない）。到着の検知は起動元が行い、必要ならこのセッションに指示を送る。
3. 起動元から『レビュー対応して』と来たら、全レビュー（インラインと本文の両方）を読み、提案として実態と照合して対応分を実装・push する。
   判断結果は PR 本文の対応表（指摘/判定/対応/根拠）に書き、また待機する。
4. マージは起動元の明示指示があったときだけ実行する。デプロイはしない。"
fi

if [ -n "${SPINOFF_SEED_APPENDIX_CMD:-}" ]; then
  if appendix=$(bash -c "$SPINOFF_SEED_APPENDIX_CMD"); then
    [ -n "$appendix" ] && run_task="${run_task}

${appendix}"
  else
    echo "WARN: SPINOFF_SEED_APPENDIX_CMD が失敗しました（タスク文には足さずに起動を続けます）" >&2
  fi
fi

esc="${run_task//\\/\\\\}"
esc="${esc//\"/\\\"}"
esc="${esc//\$/\\\$}"
esc="${esc//\`/\\\`}"

model_opt=""
[ -n "$model" ] && model_opt="--model $(printf '%q' "$model") "
# /exit でセッションを閉じたら tmux セッションも消える（自己消滅）
inner="claude -n \"${session}\" ${model_opt}--permission-mode bypassPermissions \"${esc}\"; tmux kill-session -t ${session}"

echo "起動中: session=${session}"
echo "run_dir: ${run_dir}"
tmux new-session -d -s "${session}" -c "${run_dir}" "${inner}"

if [ -n "${SPINOFF_POST_SPAWN_CMD:-}" ]; then
  bash -c "$SPINOFF_POST_SPAWN_CMD" || echo "WARN: SPINOFF_POST_SPAWN_CMD が失敗しました（セッションは起動済み）" >&2
fi

echo ""
echo "スピンオフセッション起動しました。"
echo "  セッション名 : ${session}"
echo "  プロジェクト : ${project_path}"
[ -n "$wt_line" ] && echo "$wt_line"
if [ "$wait_mode" -eq 1 ]; then
  echo "  モード       : 待機（起動直後は着手せず概要提示して停止。『開始』で着手）"
else
  echo "  モード       : 投げっぱなし（起動直後に着手）"
fi
[ -n "$issue_id" ] && echo "  issue        : ${issue_id}"
echo "  アクセス方法 : tmux attach -t ${session}"
echo "  指示を送る   : nudge.sh ${session} \"<指示>\""
echo "  後始末       : 用が済んだら起動元が tmux kill-session -t ${session}（worktree はマージ後に reap.sh --worktrees）"
