# review

依頼からマージまでの開発フローと、PR のレビューを回すスキルとコマンド。

## スキル

| スキル | 使いどころ |
|---|---|
| `dev-flow` | 開発フローの入口。issue の対応も口頭の依頼も、構造変更の判定とアーキレビュー → 実装と自己レビュー → PR → レビュー待ち → `## 結果` → マージまでの順番と約束を持つ。自動マージはリポの `.claude/dev-flow.json` で有効にする |
| `pr-review-wait` | PR を出した直後や push の後に、レビュー bot（CodeRabbit・Codex など）の結果を待って拾う |
| `pr-rereview` | レビュー bot に再レビューを依頼する |

## コマンド

- `/review:dev-process:review-and-fix` — AI レビュー → 評価 → 修正計画 → 実装までを一続きで行う

## 他のプラグインとの関係

- スコープ外の気づきの処分は [workflow](../workflow/README.md) の `issue-ops` の判定表を参照する。無くても review 単体で使える
- `dev-flow` は issue の書き方と `## 結果` を [workflow](../workflow/README.md) の `issue-ops` に任せる。workflow が無くても、`dev-flow` に書いた最低限の手順で回る
- 自動マージのリポは、リポの `.claude/dev-flow.json`（`{"autoMerge": true}`）で決める。[guards](../guards/README.md) の設定 `merge_allowed_repos` を使っていたリポは、このファイルに移す
- GitHub の操作は GitHub コネクタが第一。`gh` はコネクタで取れないもの（ローカルの Monitor など）にだけ使う

## 前提

macOS / Linux、`python3`、`git`、`gh`、`jq`

## テスト

```bash
bash plugins/review/tests/run-all.sh
```
