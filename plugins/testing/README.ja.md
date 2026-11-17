# testing

[English](README.md) | 日本語

テストを設計して回すスキルとフック。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install testing@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `testcase-generator` | 仕様書・コード・PR から Gherkin 形式のテストケースを作る |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| testcase-lint | Edit・Write の後 | テストケースの成果物がスタイルガイドに沿っているか検証する |
| full-test-gate | セッション開始・Bash の前 | 全体テストを最後に通してからの変更量を知らせ、リリース等のコマンドを未検証の変更があれば止める |

- **full-test-gate** は既定ブランチに `.claude/full-test.json` があるプロジェクトだけで動く。ファイルは作業ツリーではなく `origin/<既定>` から読むので、ブランチが自分を判定するコマンドやゲートを書き換えられない。新しい設定や変えた設定は既定ブランチにマージし、ローカルの `origin/<既定>` を fetch してから効く（`origin` リモートが無いリポは作業ツリーを読む）。書式は [`hooks/full-test-gate.py`](hooks/full-test-gate.py) の冒頭。`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" run` で全体テストを走らせて通れば記録、`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" run --working-tree` でマージ前の作業ツリーの設定を試せる（記録はしない）、`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" status` で前回からの変更量を確認できる。フックの文面にはフルパスのコマンドが出る

## 制限

既定ブランチから設定を読むチェック（full-test-gate）が防ぐのは、ブランチの中身（コミットしたファイル・push したブランチ）で変えられるものまで。手元の git の設定と環境変数は信頼し、既定ブランチは `origin` のものを正とする。fork で作業する場合は `upstream` ではなく fork の既定ブランチになる。

## 前提

macOS / Linux、`python3`、`git`
