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

- **full-test-gate** はリポに `.claude/full-test.json` を置いたプロジェクトだけで動く。書式は [`hooks/full-test-gate.py`](hooks/full-test-gate.py) の冒頭。`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" run` で全体テストを走らせて通れば記録、`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" status` で前回からの変更量を確認できる。フックの文面にはフルパスのコマンドが出る

## 前提

macOS / Linux、`python3`、`git`
