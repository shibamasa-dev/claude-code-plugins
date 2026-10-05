---
name: spinoff-session
description: 今やっているタスクを別の Claude Code セッション（tmux 上の独立セッション＋git worktree）に切り出すライフサイクル管理スキル。既定は「待機モード」＝セッション作成後は即着手せず概要提示して停止し、ユーザーが tmux attach で「開始」と指示してから始める（投げっぱなしは --unattended 指定時のみ）。「別セッションで」「切り出して」「別プロジェクトで走らせて」「バックグラウンドで実行して」「サブセッション起動」等で発動する。macOS / Linux 専用（tmux が必要。Windows は非対応）。
---

# spinoff-session

現在のタスクを tmux 上の独立した Claude Code セッションに切り出す。同じワークスペース内の並行作業は subagent、別ワークスペース・別リポで独立して走らせるならこのスキル。

**対応 OS**: macOS / Linux。tmux が無ければ `spawn.sh` が起動前に止まる（Windows は非対応）。

## 起動条件

**ユーザーの明示指示があったときだけ使う。** `spawn.sh` は `--permission-mode bypassPermissions` で起動するため、自律起動はしない。

## フロー

### ① プロジェクト(cwd)を決める

会話から作業場所が分からなければ一覧から確認する:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/spinoff-session/scripts/list-projects.sh [root_dir]  # 既定: ~/dev
```

番号付きで表示し、「どのプロジェクトで実行しますか？」と確認する。推測で決めない。

### ② seed prompt を作る

会話の内容から、spinoff に渡すタスク文を作る。ユーザーに見せて「このプロンプトで起動しますか？」と確認してから進む。状態を変えるタスクは **「PR 作成まで（マージ・デプロイしない）」と受け入れ基準を必ず書く**。

### ③ worktree を切るか決める

| 判断 | 条件 |
|---|---|
| **切る（`--worktree`・既定）** | ファイル編集・git 操作・ビルドなど、リポの状態を変えるタスク |
| **切らない（`--no-worktree`）** | 調査・要約・レビュー文の作成など、リポを変えないタスク |

- 迷ったら切る。base は既定で `main`（今のブランチを巻き込まない）。
- 今の PR・ブランチの続きは切り出さず、今のセッションで続ける。どうしても切るなら `--base <今のブランチ>`。
- `--no-worktree` はメイン tree に未コミット変更があると拒否する（読み取り専用と確信があれば `--force-shared`。非推奨）。

### ④ 起動する

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/spinoff-session/scripts/spawn.sh [--worktree|--no-worktree] [--base <branch>] [--wait|--unattended] [--issue <ref>] [--model <name>] [--force-shared] <project_path> "<task>"
```

- **既定は待機モード（`--wait`）**: 起動直後は着手せず概要を出して止まる。ユーザーが `tmux attach -t spin_<slug>` で「開始」と言うまで動かない。
- **投げっぱなしは `--unattended`**。**issue 対応は `--issue <URL|owner/repo#N>`**（既定が unattended になり、タスク文に「PR 作成まで・マージしない・レビュー到着は起動元が知らせる」を足す）。
- `--model` を省くと Claude Code の既定モデルで起動する。
- worktree は `~/.worktrees/<repo>-<slug>`（`SPINOFF_WORKTREE_ROOT` で変更可。`list.sh`・`reap.sh` も同じ変数を見る）、ブランチは `spin/<slug>`、セッション名は `spin_<slug>`。

### ⑤ 報告する

`spawn.sh` の出力（セッション名・worktree・ブランチ・アクセス方法）をそのまま伝える。spinoff の様子はユーザーが `tmux attach` で見る。

## 起動後の役割分担

**spinoff は自分でレビューを待たず、自分で畳まない。** detached セッションは外からのイベントで起きないため、自前でレビューを待つと待機中に取りこぼす。

| やること | 担当 |
|---|---|
| 実装・コミット・PR 作成 | spinoff |
| レビュー bot の到着を待つ | **起動元**（spinoff の PR に `pr-review-wait` を使う） |
| 到着を知らせる | 起動元が `bash ${CLAUDE_PLUGIN_ROOT}/skills/spinoff-session/scripts/nudge.sh spin_<slug> "PR #N にレビューが来たので対応して"` |
| レビュー対応・push | spinoff |
| マージ判断・マージ指示 | 起動元（ユーザー判断） |
| セッションを畳む | 起動元が、マージ済み・用済みを確認して `tmux kill-session -t spin_<slug>` |

## 後始末

- **完了したら畳む。溜めない。** 並列セッションが増えると、アカウント共有の rate limit 経由で Remote Control が 401 で切れ、並列数を減らすまで戻らないことがある（約 20 並列で発生した実例あり。upstream の anthropics/claude-code#32642 は NOT_PLANNED）。
- **`claude "<task>"` はタスク完了後も idle で残り、自動では `/exit` しない。** `/exit` したときだけ tmux セッションも消える。
- **畳んでも作業は失われない。** セッションを kill しても worktree・ブランチ・コミット・PR は残る。
- **保険の掃除**: `bash ${CLAUDE_PLUGIN_ROOT}/skills/spinoff-session/scripts/reap.sh --idle <分>` で一定時間 idle の `spin_` セッションを畳む。定期実行するなら閾値は「同日の待機セッションは残し、完了済みは半日以上残さない」くらいにする。
- **worktree の掃除**: `bash ${CLAUDE_PLUGIN_ROOT}/skills/spinoff-session/scripts/reap.sh --worktrees`（既定 dry-run、`--force` で実削除）。`~/.worktrees` 配下で、クリーンかつ main に取り込み済み（squash は PR の状態で判定）で 24 時間触っていないものだけ消す。**未マージの worktree は消さない。**

## 使う人ごとの差し込み口

報告先・追跡台帳など、使う人ごとの仕組みは環境変数で差し込む（どちらも任意。失敗しても起動は続ける）。

| 環境変数 | いつ | 使い道 |
|---|---|---|
| `SPINOFF_SEED_APPENDIX_CMD` | 起動前 | 標準出力をタスク文の末尾に足す（報告経路・節目の通知方法など） |
| `SPINOFF_POST_SPAWN_CMD` | tmux 起動後 | 追跡台帳への登録など |

どちらにも `SPINOFF_SESSION` / `SPINOFF_PROJECT` / `SPINOFF_RUN_DIR` / `SPINOFF_BRANCH` / `SPINOFF_ISSUE` を渡す。

## スクリプト

どれも `${CLAUDE_PLUGIN_ROOT}/skills/spinoff-session/scripts/` にある（プロジェクトの cwd からの相対パスではない）。

| スクリプト | 用途 |
|---|---|
| `spawn.sh` | spinoff セッションを起動する |
| `nudge.sh <session> "<message>"` | 稼働中の spinoff に指示を1行送る |
| `list-projects.sh [root]` | git リポジトリを番号付きで列挙する |
| `list.sh` | 稼働中の `spin_` セッションと spin worktree を一覧する |
| `reap.sh [--all \| --idle <分> \| --worktrees [--force]]` | セッション・worktree を掃除する（既定 dry-run） |

## やってはいけないこと

- ユーザーの指示なしに起動する
- `spin_` 接頭辞以外の tmux セッションに触れる
- spinoff 側で、自分からレビューを待つ・ポーリングする
- 未マージの worktree を消す
