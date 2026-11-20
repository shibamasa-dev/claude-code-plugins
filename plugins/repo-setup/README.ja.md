# repo-setup

[English](README.md) | 日本語

リポの立ち上げのスキル。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install repo-setup@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `codebase-doctor` | リポに必要な基本（テスト・CI・lint・セキュリティの初期設定など）がそろっているかの点検。空のリポでは目的を聞いて技術スタックを提案し、決めた内容を CLAUDE.md に記録する |
| `remote-setup` | claude.ai/code や Cowork のクラウド環境用のセットアップ scaffold を作る |
| `verification-skill-builder` | 実アプリを隔離した環境で台本の順に叩き、観測した証拠を残すプロジェクト専用の `verify-<app>` スキルと、機能ごとの「操作 → コマンド → 結果」の地図を作る |

`codebase-doctor` のテスト設計の点検（Check 6b）は、[testing](../testing/README.ja.md) の `testcase-generator` が持つ置き場の定義を読む。testing が入っていなければその点検は SKIP（点数から除外）にする。

## 設定

### ファイルの置き場

| 何か | 置き場 |
|---|---|
| codebase-doctor のレポート | リポの `.context/repo-setup/doctor/`。先に `.context/` を `.git/info/exclude` に足すので git には入らない |
| スキルが用意してコミットするもの | リポの中: `CLAUDE.md` の Decided setup の節、`.claude/skills/verify-<app>/`、`scripts/remote-setup/` |
| 生成したセットアップスクリプトのログ | 動かしたマシンの `~/.cache/remote-setup/<リポ名>.log` |

プラグインのデータディレクトリには何も置かないので、アンインストールしてもこれらのファイルは消えない。

## 前提

macOS / Linux、`python3`、`git`、`gh`

## テスト

```bash
bash plugins/repo-setup/tests/run-all.sh
```
