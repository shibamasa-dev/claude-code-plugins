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
| `python-venv` | venv の置き場を決める（そのリポだけなら `.venv`、別のリポや worktree からも使うなら用途ごとの共有 venv）。共有 venv を壊さずにパッケージを足し、死んだ venv を読むだけの棚卸し → `uv pip freeze` → 削除の順で掃除する |

`codebase-doctor` のテスト設計の点検（Check 6b）は、[testing](../testing/README.ja.md) の `testcase-generator` が持つ置き場の定義を読む。testing が入っていなければその点検は SKIP（点数から除外）にする。

## 設定

`userConfig` のキー。プラグインを有効にするときか、あとから `/plugin` で設定する:

| キー | 既定値 | 意味 |
|---|---|---|
| `shared_venv_dir` | `~/.venvs` | 複数のリポや worktree から使う venv を用途ごとに置くフォルダ。python-venv は共有 venv をここに作り、棚卸しでここを見る。空なら `~/.venvs` |

### ファイルの置き場

| 何か | 置き場 |
|---|---|
| codebase-doctor のレポート | リポの `.context/repo-setup/doctor/`。先に `.context/` を `.git/info/exclude` に足すので git には入らない |
| スキルが用意してコミットするもの | リポの中: `CLAUDE.md` の Decided setup の節、`.claude/skills/verify-<app>/`、`scripts/remote-setup/` |
| 生成したセットアップスクリプトのログ | 動かしたマシンの `~/.cache/remote-setup/<リポ名>.log` |

python-venv 自身は何も書かない（棚卸しのスクリプトは読むだけ）。消す前に作る `requirements-frozen-<venv 名>-<日付>.txt` は、消す venv の隣に置く。

プラグインのデータディレクトリには何も置かないので、アンインストールしてもこれらのファイルは消えない。

## 前提

macOS / Linux、`python3`、`git`、`gh`。python-venv のインストールと freeze の手順には `uv`（棚卸しは `python3` だけで動く）

## テスト

```bash
bash plugins/repo-setup/tests/run-all.sh
```
