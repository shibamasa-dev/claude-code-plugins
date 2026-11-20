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

- **full-test-gate** は既定ブランチに `.claude/full-test.json` があるプロジェクトだけで動く。ファイルは作業ツリーではなく `origin/<既定>` から読むので、ブランチが自分を判定するコマンドやゲートを書き換えられない。新しい設定や変えた設定は既定ブランチにマージし、ローカルの `origin/<既定>` を fetch してから効く（`origin` リモートが無いリポは作業ツリーを読む）。書式は [`hooks/full-test-gate.py`](hooks/full-test-gate.py) の冒頭。`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" run` で全体テストを走らせて通れば記録、`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" run --working-tree` でマージ前の作業ツリーの設定を試せる（記録はしない）、`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/full-test-gate.py" status` で前回からの変更量を確認できる。フックの文面には、フルパスで `CLAUDE_PLUGIN_DATA=...` を前置きした `run` のコマンドが出る。そこから写して使い、`status` と `run --working-tree` にも同じ前置きを付ける。Bash にはこの変数が渡らないので、前置きの無いコマンドはフックとは別のディレクトリを読み書きする

## 設定

### ファイルの置き場

| 何か | 置き場 | アンインストールで消えるか |
|---|---|---|
| full-test-gate の記録（プロジェクトごとの最後の全体テスト） | `${CLAUDE_PLUGIN_DATA}/full-test/`（`~/.claude/plugins/data/<プラグイン ID>/`）。`FULL_TEST_STATE_DIR` で動かせる。変数なしで動いたときは `~/.claude/state/testing/full-test/` | 消える（最後の scope から外したとき。`--keep-data` を付ければ残る。`FULL_TEST_STATE_DIR` で指した先は消えない） |
| `origin` を引けなかった印 | `<git common dir>/full-test-gate-origin-miss` | 消えない |
| `testcase-generator` のテストケース | リポに既にあるテストケースのファイルの隣、無ければ `docs/testcases/<テーマ>.md`。読むだけで残さないならセッションの scratchpad | 消えない |

```bash
claude plugin uninstall testing@shibamasa-plugins --keep-data
```

古い版から上げると、最初の実行で `~/.claude/state/full-test/` を新しい置き場に一度だけコピーし、古いディレクトリはバックアップとして残す。Bash には `CLAUDE_PLUGIN_DATA` が渡らないので、フックが示す `run` のコマンドは `CLAUDE_PLUGIN_DATA=...` で始まる。この前置きを外すと、フックが見ない場所に記録される。

## 制限

既定ブランチから設定を読むチェック（full-test-gate）が防ぐのは、ブランチの中身（コミットしたファイル・push したブランチ）で変えられるものまで。手元の git の設定と環境変数は信頼し、既定ブランチは `origin` のものを正とする。fork で作業する場合は `upstream` ではなく fork の既定ブランチになる。origin の既定ブランチが分からないとき（使える手元の `origin/HEAD` が無く、origin にも届かない）、チェックは動かず、その旨を出し、origin に聞き直すのは 1 時間以上あとになる。プロジェクトの `.claude/settings.json` はプラグインを無効にでき（`enabledPlugins`）、セッションの環境変数も設定できる（`env`）。このファイルを変える PR は人が差分を見る必要がある。止められるのは managed settings だけ。

## 前提

macOS / Linux、`python3`、`git`
