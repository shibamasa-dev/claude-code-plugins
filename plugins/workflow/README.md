# workflow

依頼からマージまでの開発フローと、issue とセッションの運用を型にするスキルとフック。PR のレビューの振り分けと待ち方は [review](../review/README.md)、テスト設計は [testing](../testing/README.md)、リポの立ち上げは [devtools](../devtools/README.md) に分けた。

## スキル

| スキル | 使いどころ |
|---|---|
| `dev-flow` | 開発フローの入口。issue の対応も口頭の依頼も、構造変更の判定とアーキレビュー → 実装と自己レビュー → PR → レビュー待ち → `## 結果` → マージまでの順番と約束を持つ。レビューの段は review プラグインの `pr-review-triage` に任せる。自動マージはリポの `.claude/dev-flow.json` で有効にする |
| `issue-ops` | issue の起票から close までの規約（本文の書き方、close 前の結果の書き戻し） |
| `session-wrap` | セッションを閉じる前の残件確認と、次回への引き継ぎ |
| `context-diet` | セッション開始時に毎回積まれるコンテキストを実測して減らす |
| `weekly-orchestrator-base` | 週単位で「計画 → 委譲 → 確認 → 締め」を回すオーケストレータの土台 |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| handoff | セッション開始 | 前のセッションが残した「次の入口」を注入する。書く・消すは `handoff` コマンド |
| issue-writeback | セッション開始・プロンプト送信・停止・終了、issue 操作の後 | 読んだ issue に決定事項を書き戻していなければ促す |
| runbook | ブラウザ・画面操作の後、停止、セッション開始 | ブラウザ・画面操作の手順を記録し、手順書を書き忘れたら止める |
| knowledge-freshness | セッション開始 | 見直し期限を過ぎたナレッジを 1 行で知らせる |
| artifact-ledger | Artifact の後 | 公開した Artifact をプロジェクトの `.artifacts/` に記録する |
| dev-flow-gate | PR を作る前 | 本文に `Closes #N` / `Refs #N`（issue の無い依頼は `Refs: none (verbal request)`）と `Arch-Review:` の欄が無ければ止める |
| | PR を作った後 | 次の段（レビューと CI を待つ）を伝える |
| | ターンを終える前 | このセッションで作った PR の待ち（PR イベントの購読か Monitor）を始めていなければ、PR ごとに1回だけ止める |
| | マージの前 | このセッションで作った PR の `Closes` 先の issue に、`## 結果` を書いた・読んで確かめた記録が無ければ止める |

dev-flow-gate は GitHub コネクタ（`create_pull_request`・`merge_pull_request`・`enable_pr_auto_merge`・`issue_read`・`issue_write`）と `gh` の両方を見る。GitHub を自分では読みに行かず、判定に使うのはセッション中のツール呼び出しだけ（別のセッションで作った PR のマージは止めず、確かめるよう一言返す）。状態は `${CLAUDE_PLUGIN_DATA}/dev-flow-gate/<session_id>.json` に置き、30 日より古いものはセッションの開始時に消す。

## 組織の値

組織の値（GitHub 組織・既定リポ・Issue Fields・プロジェクトボード）はスキルに持たない。セッション文脈に「組織設定」という見出しの注入テキストがあればそれを、無ければプロジェクトの CLAUDE.md を読む。社内向けの値は別のプラグインから SessionStart フックで注入する想定。

## 保存先

| 環境変数 | 既定 | 中身 |
|---|---|---|
| `HANDOFF_STATE_DIR` | `~/.claude/state/handoff` | handoff の入口 |
| `RUNBOOK_ROOT` | `~/.claude/runbooks` | runbook の生ログと手順書 |

## 前提

macOS / Linux、`python3`、`git`、`gh`

## テスト

```bash
bash plugins/workflow/tests/run-all.sh
```
