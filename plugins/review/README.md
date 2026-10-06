# review

PR のレビューを回すスキルとコマンド。

## スキル

| スキル | 使いどころ |
|---|---|
| `pr-review-wait` | PR を出した直後や push の後に、レビュー bot（CodeRabbit・Codex など）の結果を待って拾う |
| `pr-rereview` | レビュー bot に再レビューを依頼する |

## コマンド

- `/review:dev-process:review-and-fix` — AI レビュー → 評価 → 修正計画 → 実装までを一続きで行う

## 他のプラグインとの関係

- スコープ外の気づきの処分は [workflow](../workflow/README.md) の `issue-ops` の判定表を参照する。無くても review 単体で使える
- マージを Claude に任せてよいリポは [guards](../guards/README.md) の設定 `merge_allowed_repos` を見る

## 前提

macOS / Linux、`python3`、`git`、`gh`、`jq`

## テスト

```bash
bash plugins/review/tests/run-all.sh
```
