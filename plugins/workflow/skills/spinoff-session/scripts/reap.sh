#!/usr/bin/env bash
# reap.sh - spin_ セッション / spin worktree 掃除
# Usage:
#   reap.sh                    # dry-run: 消す対象を表示するだけ
#   reap.sh --all              # 全 spin_ セッションを kill
#   reap.sh --idle <分>        # 指定分以上 idle な spin_ のみ kill
#   reap.sh --worktrees        # dry-run: main 取り込み済みの worktree（~/.worktrees 配下）を表示
#   reap.sh --worktrees --force # 上記を実際に削除
#
# 安全ガード: セッションは spin_ 接頭辞のみ。worktree は ~/.worktrees 配下の追加 worktree のみ（単独 clone は触らない）
#
# ★「main に取り込み済み(merged)」判定は squash merge を検出できる形にする:
#   squash merge 運用のリポでは、squash は branch のコミットとは別 SHA の単一
#   コミットを main に作るため、`git merge-base --is-ancestor $branch main` は squash-merged
#   ブランチを永久に「未マージ」と誤判定し、worktree が溜まり続ける（今朝 42 個→argv E2BIG）。
#   よって merged 判定は次の OR にする（どちらの arm も「作業が main に入った」ことの十分条件・緩めない）:
#     ① git トポロジー: `merge-base --is-ancestor`（fast-forward / merge-commit を捕捉）
#     ② PR 状態: このブランチ head の MERGED PR の head commit が現 HEAD と一致するか（gh・squash を捕捉）
#   gh 不在・エラー・0 件・head 不一致はすべて「未マージ扱い＝保持」にフォールバックする（安全側）。
#   ※ worktree 内の local main は stale なことがある（fetch 前）。その場合 ① は本当の merge も
#     false になり得るが、② の PR 状態が拾うため hybrid が安全。
#
# ★worktree 削除の活性ガード（誤削除防止・2026-07 追加）:
#   git トポロジーでは「作業が main に取り込まれた merged」と「main から切っただけで
#   まだ 1 コミットもしていない稼働中セッション」を区別できない（どちらも main の祖先＝
#   `merge-base --is-ancestor` が true・0 コミット差）。よって clean+merged だけで削除すると
#   着手前の稼働 worktree を巻き込む。これを防ぐため、削除前に「活性」を2軸でチェックし保持する:
#     ① tmux 上に、この worktree 配下を cwd とする稼働中 spin_ セッションがある（idle < 閾値）
#     ② worktree 配下に、閾値内に更新されたファイルがある（.git/node_modules/.venv 除く）
#   閾値は env REAP_WT_IDLE_MIN（既定 1440 分＝24h・セッション kill 側の --idle 1440 と対称）。
set -euo pipefail

# worktree 活性ガードの idle 閾値（分）。この時間内に活動があれば merged/clean でも保持する。
wt_idle_min="${REAP_WT_IDLE_MIN:-1440}"

# worktree の探索ルート（既定 $HOME/.worktrees）。REAP_WT_IDLE_MIN と同様に env で上書き可能。
# テスト・非標準配置で使う（本番は既定のまま）。
wt_root="${REAP_WT_ROOT:-$HOME/.worktrees}"

# このブランチの現 HEAD が MERGED PR の head commit と一致するか判定する（squash merge 検出用）。
#   戻り値: 0=現 HEAD と一致する MERGED PR あり / 1=無い・不明（gh 不在/エラー/0 件）。
#   gh が使えない・失敗する場合は 1（未マージ扱い＝保持）にフォールバックし、絶対に緩めない。
#   引数: $1=worktree パス（PR 解決のため gh をその worktree の remote 文脈で走らせる）/ $2=ブランチ名。
#
#   ★名前一致だけでは不十分: `--head "$br"` は過去や別 fork の同名 merged PR も拾う。
#     squash merge 済みブランチに後から未マージ commit を積んだ場合、名前一致だと merged=1 になり
#     現作業を消しかねない。よって MERGED PR の headRefOid が現在の HEAD と厳密一致する場合のみ真とする。
_branch_pr_merged() {
  local wt="$1" br="$2" head_oid oids
  command -v gh >/dev/null 2>&1 || return 1
  # worktree の現在の HEAD commit。取得不能なら未マージ扱い（保持）。
  head_oid=$(git -C "$wt" rev-parse HEAD 2>/dev/null) || return 1
  [ -n "$head_oid" ] || return 1
  # gh はカレントディレクトリの remote からリポジトリを解決するため worktree 内で実行する。
  # --head でこのブランチ head の PR に絞り、--state merged で MERGED のみ、その head commit を列挙。
  oids=$( cd "$wt" && gh pr list --head "$br" --state merged --json headRefOid --jq '.[].headRefOid' 2>/dev/null ) || return 1
  # 列挙した head commit（1 行 1 SHA）の中に現 HEAD と完全一致する行があるか（-x=行全体一致）。
  if printf '%s\n' "$oids" | grep -qxF "$head_oid"; then
    return 0
  fi
  return 1
}

mode="dry-run"
idle_threshold_min=0
do_worktrees=0
force=0

# 引数パース
while [ $# -gt 0 ]; do
  case "$1" in
    --all)
      mode="all"
      shift
      ;;
    --idle)
      if [ -z "${2:-}" ]; then
        echo "ERROR: --idle には分数を指定してください" >&2
        exit 1
      fi
      mode="idle"
      idle_threshold_min="$2"
      shift 2
      ;;
    --worktrees)
      do_worktrees=1
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    *)
      echo "Usage: reap.sh [--all | --idle <分> | --worktrees [--force]]" >&2
      exit 1
      ;;
  esac
done

# ===== worktree 掃除モード（session ロジックに入る前に分岐して exit）=====
if [ "$do_worktrees" -eq 1 ]; then
  if [ ! -d "$wt_root" ]; then
    echo "対象なし（$wt_root が存在しません）"
    exit 0
  fi

  now_epoch=$(date +%s)

  # ① 稼働中 spin_ セッションの cwd 一覧を「idle分<TAB>cwd」で収集（活性ガード用）。
  #    tmux が無い/セッション0でも空ファイルで安全に続行する。
  live_sessions_file=$(mktemp "${TMPDIR:-/tmp}/reap-live.XXXXXX")
  # NOTE: process substitution `< <(...)` は bash 専用で、scheduler が `sh reap.sh` で
  # 起動すると line で syntax error になり毎 tick 失敗する。ループ本体は
  # $live_sessions_file への追記のみ（サブシェルで変数を持ち帰る必要が無い）ので、
  # POSIX で安全な pipe 形に置き換える。
  { tmux list-sessions -F '#{session_name} #{session_activity}' 2>/dev/null || true; } | while IFS=' ' read -r sname sactivity; do
    case "$sname" in spin_*) ;; *) continue ;; esac
    [ -n "${sactivity:-}" ] || continue
    scwd=$(tmux display-message -p -t "$sname" '#{pane_current_path}' 2>/dev/null) || continue
    [ -n "$scwd" ] || continue
    s_idle_min=$(( (now_epoch - sactivity) / 60 ))
    printf '%s\t%s\n' "$s_idle_min" "$scwd" >> "$live_sessions_file"
  done

  # ② ファイル更新時刻ガード用の基準ファイル（mtime = now - wt_idle_min 分）。
  #    これより新しいファイルが worktree 配下にあれば「最近活動あり」と判定する。
  cutoff_epoch=$(( now_epoch - wt_idle_min * 60 ))
  cutoff_ref=$(mktemp "${TMPDIR:-/tmp}/reap-cutoff.XXXXXX")
  cutoff_stamp=$(date -r "$cutoff_epoch" +%Y%m%d%H%M.%S 2>/dev/null \
                 || date -d "@$cutoff_epoch" +%Y%m%d%H%M.%S 2>/dev/null || echo "")
  [ -n "$cutoff_stamp" ] && touch -t "$cutoff_stamp" "$cutoff_ref" 2>/dev/null || true

  # worktree が「活性」か判定（稼働セッション or 最近のファイル更新があれば 1）。
  _wt_is_active() {
    local wt="$1" line idle cwd
    # ① 稼働中 spin_ セッションがこの worktree 配下で動いている（idle < 閾値）
    if [ -s "$live_sessions_file" ]; then
      while IFS=$'\t' read -r idle cwd; do
        case "$cwd" in
          "$wt"|"$wt"/*)
            if [ "${idle:-999999}" -lt "$wt_idle_min" ]; then return 0; fi
            ;;
        esac
      done < "$live_sessions_file"
    fi
    # ② 閾値内に更新されたファイルがある（.git/node_modules/.venv は除外）
    #    cutoff_ref は mtime 比較用の 0 バイト基準ファイルなので存在判定は -e で行う。
    #    以前は -s（サイズ>0）で判定しており、常に空＝この活性ガードが恒常的に skip され、
    #    ファイル更新のみで活動している worktree を保護できていなかった。
    if [ -e "$cutoff_ref" ]; then
      local hit
      hit=$(find "$wt" -type f \
              -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' \
              -newer "$cutoff_ref" -print 2>/dev/null | head -n 1)
      [ -n "$hit" ] && return 0
    fi
    return 1
  }

  found=0
  removed=0
  for wt in "$wt_root"/*/; do
    [ -d "$wt" ] || continue
    wt="${wt%/}"

    # git worktree でなければスキップ
    git -C "$wt" rev-parse --git-dir >/dev/null 2>&1 || continue

    # HEAD ブランチを取得（detached/取得失敗はスキップ）
    branch=$(git -C "$wt" symbolic-ref --short -q HEAD 2>/dev/null) || continue

    # 対象は ~/.worktrees 配下の「追加 worktree」すべて（2026-10-04 Masa 承認で spin/* 限定を外した。
    # spinoff 以外で作った worktree が溜まり続けていたため）。削除条件（clean・merged・非活性）は共通。
    # 安全ガード: 単独 clone（その場所自体がメイン worktree）は worktree remove できず、
    # 消すと clone ごと失われるので触らない。git-dir と common-dir が同じならメイン worktree。
    if [ "$(git -C "$wt" rev-parse --absolute-git-dir 2>/dev/null)" = \
         "$(cd "$wt" && cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)" ]; then
      continue
    fi
    # main / master そのものを checkout した worktree は merged 判定が常に真になり、
    # 後段の branch -D がローカルの main を消しうるので対象外
    case "$branch" in main|master) continue ;; esac

    found=$((found + 1))

    # ① 作業ツリーに「回収すべきもの」が残っているか（main 基準で見る）
    #
    #    従来は `git status --porcelain` が空かどうかで判定していたが、これは
    #    **worktree 自身の HEAD** に対する差分であって main 基準ではない。
    #    spin worktree の HEAD は作成時点で固定されるため、その後 main 側へ同じ内容が
    #    入ると（squash merge や別経路での取り込み）「内容は main と同一なのに
    #    status は modified」という状態が恒久的に残り、reap が一生削除できずに
    #    worktree が累積する。
    #
    #    実測（2026-07-25）: spin worktree 5件が 7〜12 日滞留していた。modified 表示の
    #    ファイルは全て main と内容一致（issue-25 の doc は sha256 が main と同一、
    #    issue-20 の5ファイルは main との diff 0行）＝**回収漏れはゼロ**で、保持理由だけが
    #    永久に消えない状態だった。worktree の累積は Remote Control を殺す実績があるため
    #    （並列約23で /bridge 401 恒久 death）、判定を正確にする必要がある。
    #
    #    よって main 基準に変える:
    #      - tracked: **status が変更ありと言ったファイルだけ**を main と比較し、どれかが
    #        main の内容と違えば未回収。
    #        ⚠️ `git diff main`（全 tracked を比較）ではダメ: spin worktree の HEAD は古いので
    #        main が進んだぶん**無関係なファイルまで差分**になり、stale な worktree は
    #        常に「未回収」と判定されてしまう（この実装で1度踏んだ）。
    #      - untracked: 作業用スクラッチ（spinoff-work*）を除いて残るものがあるか
    #    どちらかが真なら「回収すべきものがある」＝保持。`git diff` がエラーを返す場合
    #    （main が無い等）も非ゼロ終了なので保持側に倒れる＝安全側。
    clean=1
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      # HEAD 基準で変更のある tracked ファイル（staged / unstaged 両方）を main と比較する。
      #
      # NOTE: ここも process substitution `< <(...)` を使わない（bash 専用）。
      #   ①の live_sessions_file と同じ理由で、scheduler が `sh reap.sh` で起動すると
      #   この行で syntax error になり **両アームとも毎 tick 完全な no-op** になる。
      #   2026-07-25 に main 基準の判定を足したとき、①で一度潰したはずの構文が
      #   ここで再導入されていた（repo 版には main 基準の判定自体が無く、live 版には
      #   POSIX 化が無い、という相互欠落の正体がこれ）。
      #   ループ本体から変数を持ち帰れないので、ミスマッチを一時ファイルへ記録して判定する。
      #
      # ⚠️ -z を tr で改行へ直しているため、パスに**改行を含む**ファイルだけは正しく扱えない。
      #   空白・UTF-8 は正しく通る。git は既定でそれ以外の特殊文字を quote するので、
      #   quote された名前は `git diff -- "$f"` が一致せず「差分あり」＝保持側に倒れる（安全側）。
      #
      # ⚠️ `set -euo pipefail` なので、git 側が失敗したときにパイプライン全体が非ゼロで
      #   落ちないよう `|| true` で受ける（①と同じ作法）。
      mismatch_file=$(mktemp "${TMPDIR:-/tmp}/reap-mismatch.XXXXXX")
      { git -C "$wt" diff --name-only -z HEAD 2>/dev/null || true; } | tr '\0' '\n' \
        | while IFS= read -r f; do
            [ -n "$f" ] || continue
            if ! git -C "$wt" diff --quiet main -- "$f" 2>/dev/null; then
              printf '1\n' >> "$mismatch_file"
            fi
          done
      if [ -s "$mismatch_file" ]; then
        clean=0
      fi
      rm -f "$mismatch_file"
      if [ "$clean" -eq 1 ]; then
        # ⚠️ このスクリプトは `set -euo pipefail`。
        #  - `grep -v` は全行除外されると exit 1 を返し、pipefail で代入が失敗扱いになる
        #  - `[ cond ] && action` を単独文で書くと cond が偽のとき文全体が非ゼロになり
        #    set -e でスクリプトが即死する（この実装で1度踏んだ）
        #  よって `|| true` で受けて、判定は明示 if で書く。
        untracked_left=$(git -C "$wt" ls-files --others --exclude-standard 2>/dev/null \
                          | grep -v '^spinoff-work' || true)
        if [ -n "$untracked_left" ]; then
          clean=0
        fi
      fi
    fi

    # ② ブランチが main に取り込み済みか（squash merge を検出できる hybrid 判定）
    #    arm①: トポロジー的祖先（fast-forward / merge-commit）。arm②: PR が MERGED（squash）。
    #    どちらか一方でも真なら merged。gh 不在・エラー・stale local main は ② が拾えなければ
    #    自然に merged=0（保持）へ倒れる＝安全側。
    merged=0
    if git -C "$wt" merge-base --is-ancestor "$branch" main >/dev/null 2>&1; then
      merged=1
    elif _branch_pr_merged "$wt" "$branch"; then
      merged=1
    fi

    # ③ 活性ガード: 稼働セッション or 最近のファイル更新があれば merged/clean でも保持。
    active=0
    if _wt_is_active "$wt"; then
      active=1
    fi

    if [ "$clean" -eq 1 ] && [ "$merged" -eq 1 ] && [ "$active" -eq 0 ]; then
      if [ "$force" -eq 1 ]; then
        # メイン worktree 経由で削除（対象 worktree 自身からは削除しない）。
        # worktree 行のパスは空白を含みうるので $2 でなく "worktree " prefix だけ外す。
        main_wt=$(git -C "$wt" worktree list --porcelain | awk '/^worktree /{sub(/^worktree /, ""); print; exit}')
        echo "削除: $wt (branch: $branch)"
        # `git worktree remove` は作業ツリーに modified/untracked があると素で拒否する。
        # ここへ来るのは clean 判定（＝main に無い変更が無い／untracked は作業スクラッチのみ）を
        # 通過したケースだけなので、その残渣を落とすために --force を渡す。
        # ⚠️ この --force は「回収すべきものが無いと確認済み」という上の条件に厳密に紐づいている。
        #    clean 判定を緩めるとここが破壊的になるので、両者はセットで変更すること。
        #    （2026-07-25: clean を main 基準にした結果、この拒否で削除が全件失敗して判明）
        if git -C "$main_wt" worktree remove --force "$wt"; then
          # squash-merged branch はトポロジー的には未マージのため `branch -d` は失敗して残る。
          # この分岐は merged 判定（トポロジー or PR-merged head 一致）を通過済みなので -D で確実に消す。
          if git -C "$main_wt" branch -D -- "$branch"; then
            removed=$((removed + 1))
          else
            echo "  (branch 削除失敗: $branch)" >&2
          fi
        else
          echo "  (worktree remove 失敗: $wt)" >&2
        fi
      else
        echo "[dry-run] 削除候補: $wt (branch: $branch, クリーン/マージ済み/非活性)"
      fi
    else
      reason=""
      [ "$clean" -eq 0 ] && reason="main に無い変更あり（未回収）"
      [ "$merged" -eq 0 ] && reason="${reason:+$reason / }未マージ"
      [ "$active" -eq 1 ] && reason="${reason:+$reason / }活性（稼働セッション/最近${wt_idle_min}分内の更新）"
      echo "[保持] $wt (branch: $branch) - $reason"
    fi
  done

  rm -f "$live_sessions_file" "$cutoff_ref"

  if [ "$found" -eq 0 ]; then
    echo "対象なし（~/.worktrees に追加 worktree が見つかりません）"
    exit 0
  fi

  if [ "$force" -eq 1 ]; then
    echo ""
    echo "完了（削除: ${removed} 件・活性/未マージ/未コミットは保持）"
  else
    echo ""
    echo "dry-run モードです。実際に削除するには --worktrees --force を指定してください。"
  fi
  exit 0
fi

# spin_ セッション一覧を一時ファイルに取得
sessions_file=$(mktemp "${TMPDIR:-/tmp}/reap-sessions.XXXXXX")
tmux list-sessions -F '#{session_name} #{session_activity}' 2>/dev/null > "$sessions_file" || true

if [ ! -s "$sessions_file" ]; then
  echo "稼働中のセッションなし"
  rm -f "$sessions_file"
  exit 0
fi

now=$(date +%s)
targets_file=$(mktemp "${TMPDIR:-/tmp}/reap-targets.XXXXXX")

while IFS=' ' read -r name activity; do
  # 安全ガード: spin_ 接頭辞以外は絶対にスキップ
  case "$name" in
    spin_*) ;;
    *) continue ;;
  esac

  idle_sec=$(( now - activity ))
  idle_min=$(( idle_sec / 60 ))

  if [ "$mode" = "all" ]; then
    echo "$name" >> "$targets_file"
  elif [ "$mode" = "idle" ]; then
    if [ "$idle_min" -ge "$idle_threshold_min" ]; then
      echo "$name" >> "$targets_file"
    fi
  else
    # dry-run: 対象を表示
    printf "[dry-run] 対象: %-40s  idle: %d min\n" "$name" "$idle_min"
  fi
done < "$sessions_file"
rm -f "$sessions_file"

if [ "$mode" = "dry-run" ]; then
  echo ""
  echo "dry-run モードです。実際に削除するには --all または --idle <分> を指定してください。"
  rm -f "$targets_file"
  exit 0
fi

if [ ! -s "$targets_file" ]; then
  echo "削除対象の spin_ セッションはありません"
  rm -f "$targets_file"
  exit 0
fi

echo "削除するセッション:"
while IFS= read -r name; do
  # 二重チェック: spin_ 接頭辞を再確認してから kill
  case "$name" in
    spin_*)
      echo "  killing: $name"
      tmux kill-session -t "$name" 2>/dev/null || echo "  (既に消滅: $name)"
      ;;
    *)
      echo "  スキップ(spin_以外): $name" >&2
      ;;
  esac
done < "$targets_file"
rm -f "$targets_file"

echo "完了"
