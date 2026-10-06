# review

依頼からマージまでの開発フローと、PR のレビューを回すスキルとコマンド。

## スキル

| スキル | 使いどころ |
|---|---|
| `dev-flow` | 開発フローの入口。issue の対応も口頭の依頼も、構造変更の判定とアーキレビュー → 実装と自己レビュー → PR → レビュー待ち → `## 結果` → マージまでの順番と約束を持つ。自動マージはリポの `.claude/dev-flow.json` で有効にする |
| `pr-review-wait` | PR を出した直後や push の後に、レビュー bot（CodeRabbit・Codex など）の結果を待って拾う |
| `pr-rereview` | レビュー bot に再レビューを依頼する |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| dev-flow-gate | PR を作る前 | 本文に `Closes #N` / `Refs #N`（issue の無い依頼は `Refs: none (verbal request)`）と `Arch-Review:` の欄が無ければ止める |
| | PR を作った後 | 次の段（レビューと CI を待つ）を伝える |
| | ターンを終える前 | このセッションで作った PR の待ち（PR イベントの購読か Monitor）を始めていなければ、PR ごとに1回だけ止める |
| | マージの前 | このセッションで作った PR の `Closes` 先の issue に、`## 結果` を書いた・読んで確かめた記録が無ければ止める |

- GitHub コネクタ（`create_pull_request`・`merge_pull_request`・`enable_pr_auto_merge`・`issue_read`・`issue_write`）と `gh` の両方を見る
- GitHub を自分では読みに行かない。判定に使うのはセッション中のツール呼び出しだけ。別のセッションで作った PR のマージは止めず、確かめるよう一言返す
- 状態は `${CLAUDE_PLUGIN_DATA}/dev-flow-gate/<session_id>.json`。30 日より古いものはセッションの開始時に消す

## コマンド

- `/review:dev-process:review-and-fix` — AI レビュー → 評価 → 修正計画 → 実装までを一続きで行う

## 他のプラグインとの関係

- スコープ外の気づきの処分は [workflow](../workflow/README.md) の `issue-ops` の判定表を参照する。無くても review 単体で使える
- `dev-flow` は issue の書き方と `## 結果` を [workflow](../workflow/README.md) の `issue-ops` に任せる。workflow が無くても、`dev-flow` に書いた最低限の手順で回る
- 自動マージのリポは、リポの `.claude/dev-flow.json`（`{"autoMerge": true}`）で決める。[guards](../guards/README.md) の設定 `merge_allowed_repos`（非推奨）に書いたリポは、このファイルに移す。マージの前の確認は guards から dev-flow-gate に移った
- GitHub の操作は GitHub コネクタが第一。`gh` はコネクタで取れないもの（ローカルの Monitor など）にだけ使う

## 前提

macOS / Linux、`python3`、`git`、`gh`、`jq`

## テスト

```bash
bash plugins/review/tests/run-all.sh
```
