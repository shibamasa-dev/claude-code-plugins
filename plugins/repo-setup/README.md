# repo-setup

リポの立ち上げのスキル。0.3.0 で devtools から名前を変え、使用枠を書き出す mod（rate-limits）は [workflow](../workflow/README.md) へ移した。

## スキル

| スキル | 使いどころ |
|---|---|
| `codebase-doctor` | リポに必要な基本（テスト・CI・lint・セキュリティの初期設定など）がそろっているかの点検 |
| `remote-setup` | claude.ai/code や Cowork のクラウド環境用のセットアップ scaffold を作る |

`codebase-doctor` のテスト設計の点検（Check 6b）は、[testing](../testing/README.md) の `testcase-generator` が持つ置き場の定義を読む。testing が入っていなければその点検は SKIP（点数から除外）にする。

## 前提

macOS / Linux、`python3`、`git`、`gh`
