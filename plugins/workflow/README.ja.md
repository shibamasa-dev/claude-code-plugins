# workflow

[English](README.md) | 日本語

依頼からマージまでの開発フロー（PR のレビューの振り分けと待ち方を含む）と、issue とセッションの運用を型にするスキルとフック。テスト設計は [testing](../testing/README.ja.md)、リポの立ち上げは [repo-setup](../repo-setup/README.ja.md) に分けた。

0.3.0 で review プラグインをここに統合した（`pr-review-triage` スキル・`dev-process` コマンド・review の userConfig）。review を入れていたら外して、設定を下の「設定（userConfig）」のキーに入れ直す。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install workflow@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `dev-flow` | 開発フローの入口。issue の対応も口頭の依頼も、構造変更の判定とアーキレビュー → 実装と自己レビュー → PR → レビュー待ち → `## Result` → マージまでの順番と約束を持つ。レビューの段は `pr-review-triage` に任せる。自動マージはリポの `.claude/dev-flow.json` で有効にする |
| `pr-review-triage` | PR を出した直後や push の後に、差分の重さでレビューの頼み先を振り分ける。軽い PR（文書だけ・200 行以内）は `review_light` に従う。既定の `claude` なら Claude がレビューして PR 本文に書き、CI だけ待つ。ツールの id を書けば（`claude` と並べたときも）そのツールの結果も待つ。重い PR はレビューツール（CodeRabbit・Codex など）にコネクタで頼み（ツールの自動レビューを ON にしたリポでは頼まずに、軽い PR だけ `review:light` ラベルで自動レビューから外す）、結果を待って評価・対応する。再レビューを頼むかの判断と依頼もここ |
| `issue-ops` | issue の起票から close までの規約（本文の書き方、close 前の結果の書き戻し） |
| `session-wrap` | セッションを閉じる前の残件確認と、次回への引き継ぎ |
| `context-diet` | セッション開始時に毎回積まれるコンテキストを実測して減らす |
| `weekly-orchestrator-base` | リポジトリごとに 1 つ置く長寿命のオーケストレータセッション（タイトルが `🎯 <リポ名>` で始まり、ピン留めして毎日使う）の土台。週単位で「計画 → 委譲 → 確認 → 締め」を回し、PR になる作業は子セッションへ、読むだけの調査・検証は subagent へ出す。状態はサイクル issue に置くので、手動の `/clear` で何も失わない。専用のオーケストレータスキルが無いリポ向けの既定（週単位のサイクル・issue のタイトル）も持つ |
| `choice-board` | 10 個以上の項目それぞれについて決める必要があるとき、チャットではなくボードのページに出す。1 項目 1 行で、選択肢（推奨に印）とメモを並べ、Artifact のデータベースに保存して Claude が読み戻す。ボードは 1 プロジェクト 1 つを使い回す。Artifact のツール（claude.ai に接続した Claude Code）が必要 |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| handoff | セッション開始 | 前のセッションが残した「次の入口」を注入する。書くのは `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/handoff.py" write --entry <owner>/<repo>#<n> --state "..." --next "..."`、消すのは `... consume --entry <入口>`。注入される文面に実行できるコマンドがそのまま出る |
| issue-writeback | セッション開始・プロンプト送信・停止・終了、issue 操作の後 | 読んだ issue に決定事項を書き戻していなければ促す |
| runbook | ブラウザ・画面操作の後、停止、セッション開始 | ブラウザ・画面操作の手順を記録する。最初の操作で、GIF 録画の開始（Chrome）か要所のメモ（録画できないツール）を促す。手順書を書き忘れたら止める |
| orchestrator-report | PR の作成・更新、issue への書き込み（コネクタか `gh`）の後 | 同じリポジトリ（worktree を含む）で動いているセッションのうち、タイトルが `🎯` で始まるものがちょうど 1 つあり、それが自分でなければ、SendMessage で 1 行報告するよう Claude に伝える。PR / issue ごとにセッションで 1 回だけ。クラウドと Claude Projects のセッションでは動かない |
| knowledge-freshness | セッション開始 | 見直し期限を過ぎたナレッジを 1 行で知らせる |
| artifact-ledger | Artifact の後 | 公開した Artifact をプロジェクトの `.artifacts/` に記録する |
| dev-flow-gate | PR を作る前 | 本文に `Closes #N` / `Refs #N`（issue の無い依頼は `Refs: none (verbal request)`）と `Arch-Review:` の欄が無ければ止める |
| | PR を作った後 | 次の段（レビューと CI を待つ）を伝える |
| | ターンを終える前 | このセッションで作った PR の待ち（PR イベントの購読か Monitor）を始めていなければ、PR ごとに1回だけ止める |
| | マージの前 | このセッションで作った PR の `Closes` 先の issue に、`## Result`（以前の `## 結果` も可）を書いた・読んで確かめた記録が無ければ止める |

dev-flow-gate は GitHub コネクタ（`create_pull_request`・`merge_pull_request`・`enable_pr_auto_merge`・`issue_read`・`issue_write`）と `gh` の両方を見る。GitHub を自分では読みに行かず、判定に使うのはセッション中のツール呼び出しだけ（別のセッションで作った PR のマージは止めず、確かめるよう一言返す）。状態は `${CLAUDE_PLUGIN_DATA}/dev-flow-gate/<session_id>.json` に置き、30 日より古いものはセッションの開始時に消す。

## mod

| mod | 動き |
|---|---|
| `rate-limits` | 使用枠（5時間・週）を `/tmp/claude-<uid>/rate-limits.json` に書き出す。`<uid>` は `id -u`。週の残り枠を外のスクリプトが見張る用 |

出力は `{"five_hour": {"used_percentage": 17, "resets_at": 1791553800, "seen_at": 1791552278}, "seven_day": {...}}`（`resets_at`・`seen_at` は epoch 秒）。枠ごとに `resets_at` が大きい方、同じなら `used_percentage` が大きい方を残す（ベストエフォート。プロセス間のロックは無いので、並列セッションがほぼ同時に書くと一時的に古い値へ戻ることがあり、次に使用率が動いたときに直る）。値が変わらなければ書かない。出力先は本人専用（700）のディレクトリで、無ければ作る。リンク・他人所有・700 以外なら何も書かない。中で一時ファイルに書いて `mv -f` で置き換える（失敗したら書かない）。mod が動くのは Claude Code の CLI（`$.process` を使うため）。0.3.0 で devtools（今の repo-setup）から移した。

## 設定（userConfig）

| キー | 既定 | 使いどころ |
|---|---|---|
| `review_heavy` | 空 | 重い PR に使うレビューツール（カンマ区切り。例: `coderabbit,codex`。`none` はツールなし）。リポの行も設定も無ければ `pr-review-triage` がユーザーに聞く |
| `review_light` | `claude` | 軽い PR に使うもの。`claude` なら Claude がレビューする。ツールの id を書けば軽い PR も重い PR と同じ扱い（ラベルを付けない） |
| `review_auto` | `off` | ツールの自動レビューが ON か（`on` / `off`）。下の「自動レビューを ON のまま使う」 |
| `rereview_threshold` | 3 | 重い指摘（Critical・P1 相当）をこの件数以上直したときだけ再レビューを頼む |

使えるツールの id は `skills/pr-review-triage/references/tools/` のファイル名（`codex`・`coderabbit`・`copilot`・`gemini`・`cursor-bugbot`）。

リポごとに変えるなら、リポの CLAUDE.md（または AGENTS.md）に行で書く。行が userConfig より優先する。`review-notes:` は重点的に見てほしいことを自然言語で書く行で、依頼文と Claude のレビューに渡す（振り分けの判定には使わない）:

```
review-heavy: coderabbit, codex
review-light: claude
review-auto: on
review-notes: 権限まわりの変更は特に見てほしい
```

### 自動レビューを ON のまま使う（`review-auto: on`）

ツールの自動レビューを ON のままにして、軽い PR だけラベルで外す。手動の `@coderabbitai review` も CodeRabbit の上限に 1 回ずつ数えられるので、自動レビューを止めても枠は節約できない。CodeRabbit は自動レビューの制御（ラベルなど）で外した PR を上限に数えない（[rate limits](https://docs.coderabbit.ai/management/rate-limits)）。

- 軽い PR（`review-light: claude` のとき）は、PR を作る前に判定して `review:light` ラベルを付けて作る。Claude がレビューする
- 重い PR はツールが自動で走るので、依頼のコメントは投稿せず結果を待つ
- push で軽い → 重いに変わったら、ラベルを外してツールに手動で頼む
- `review-light: coderabbit, codex` のようにツールを書くと、軽い PR にもラベルを付けず、重い PR と同じ扱いになる（ラベルの運用をやめるときの戻し方）
- `review-light: claude, codex` のように `claude` とツールを並べると、軽い PR にラベルを付けて Claude がレビューし、ラベルで外れないツール（Codex など）の自動レビューの結果も待つ。ラベルで外れるツール（CodeRabbit）を並べると自動では結果が来ないので並べない

ツール側には、ラベルの付いた PR を自動レビューから外す設定を入れる。CodeRabbit ならリポの `.coderabbit.yaml` に:

```yaml
reviews:
  auto_review:
    labels: ["!review:light"]
```

`!` で始まるラベルは否定の一致（[configuration](https://docs.coderabbit.ai/reference/configuration)）。

**未確認**（実測していない）:
1. PR を作るときに付けたラベルで、CodeRabbit が最初の自動レビューの前に外すか
2. この設定を組織単位で入れられるか（入れられなければリポごとの `.coderabbit.yaml`）
3. Codex をラベルで自動レビューから外せるか（外せなければ軽い PR でも Codex は走る）

## コマンド

- `/workflow:dev-process:review-and-fix` — AI レビュー → 評価 → 修正計画 → 実装までを一続きで行う

## 組織の値

組織の値（GitHub 組織・既定リポ・Issue Fields・プロジェクトボード）はスキルに持たない。セッション文脈に「Organization settings」か「組織設定」という見出しの注入テキストがあればそれを、無ければプロジェクトの CLAUDE.md を読む。社内向けの値は別のプラグインから SessionStart フックで注入する想定。

## 保存先

| 環境変数 | 既定 | 中身 |
|---|---|---|
| `HANDOFF_STATE_DIR` | `~/.claude/state/handoff` | handoff の入口 |
| `RUNBOOK_ROOT` | `~/.claude/runbooks` | runbook の生ログと手順書 |

## 制限

- orchestrator-report はオーケストレータを `claude agents --json` で探す。これはプロセスが動いているセッションしか返さないため、オーケストレータのプロセスが動いていない間（アプリの再起動後、そのセッションを開き直すまで等）は報告を促さない
- クラウドのセッションと Claude Projects のセッションは、手元のオーケストレータに報告しない（手元のセッションへメッセージを送れないため）

## 前提

macOS / Linux、`python3`、`git`、`gh`、`jq`

## テスト

```bash
bash plugins/workflow/tests/run-all.sh
claude plugin test plugins/workflow   # rate-limits mod
```
