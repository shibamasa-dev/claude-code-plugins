# workflow

issue・PR・セッションの運用を型にするスキルとフック。

## スキル

| スキル | 使いどころ |
|---|---|
| `issue-ops` | issue の起票から close までの規約（本文の書き方、close 前の結果の書き戻し） |
| `pr-review-wait` | PR を出した直後や push の後に、レビュー bot（CodeRabbit・Codex など）の結果を待って拾う |
| `pr-rereview` | レビュー bot に再レビューを依頼する |
| `session-wrap` | セッションを閉じる前の残件確認と、次回への引き継ぎ |
| `codebase-doctor` | リポに必要な基本（テスト・CI・lint・セキュリティの初期設定など）がそろっているかの点検 |
| `context-diet` | セッション開始時に毎回積まれるコンテキストを実測して減らす |
| `remote-setup` | claude.ai/code や Cowork のクラウド環境用のセットアップ scaffold を作る |
| `weekly-orchestrator-base` | 週単位で「計画 → 委譲 → 確認 → 締め」を回すオーケストレータの土台 |
| `openapi-to-skills` | OpenAPI 定義から API 操作のスキルを生成する（`uv` が要る） |
| `testcase-generator` | 仕様書・コード・PR から Gherkin 形式のテストケースを作る |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| handoff | セッション開始 | 前のセッションが残した「次の入口」を注入する。書く・消すは `handoff` コマンド |
| issue-writeback | セッション開始・プロンプト送信・停止・終了、issue 操作の後 | 読んだ issue に決定事項を書き戻していなければ促す |
| runbook | ブラウザ・画面操作の後、停止、セッション開始 | ブラウザ・画面操作の手順を記録し、手順書を書き忘れたら止める |
| knowledge-freshness | セッション開始 | 見直し期限を過ぎたナレッジを 1 行で知らせる |
| artifact-ledger | Artifact の後 | 公開した Artifact をプロジェクトの `.artifacts/` に記録する |
| testcase-lint | Edit・Write の後 | テストケースの成果物がスタイルガイドに沿っているか検証する |

## コマンド

- `/workflow:dev-process:review-and-fix` — AI レビュー → 評価 → 修正計画 → 実装までを一続きで行う

## 組織の値

組織の値（GitHub 組織・既定リポ・Issue Fields・プロジェクトボード）はスキルに持たない。セッション文脈に「組織設定」という見出しの注入テキストがあればそれを、無ければプロジェクトの CLAUDE.md を読む。社内向けの値は別のプラグインから SessionStart フックで注入する想定。

## 保存先

| 環境変数 | 既定 | 中身 |
|---|---|---|
| `HANDOFF_STATE_DIR` | `~/.claude/state/handoff` | handoff の入口 |
| `RUNBOOK_ROOT` | `~/.claude/runbooks` | runbook の生ログと手順書 |

## 前提

macOS / Linux、`python3`、`git`、`gh`。`openapi-to-skills` は `uv`

## テスト

```bash
bash plugins/workflow/tests/run-all.sh
```
