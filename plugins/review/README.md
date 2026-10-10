# review

PR のレビューを回すスキルとコマンド。依頼からマージまでの開発フロー（`dev-flow`）は [workflow](../workflow/README.md) にある。

## スキル

| スキル | 使いどころ |
|---|---|
| `pr-review-triage` | PR を出した直後や push の後に、差分の重さでレビューの頼み先を振り分ける。軽い PR（文書だけ・200 行以内）は Claude がレビューして PR 本文に書き、CI だけ待つ。重い PR はレビューツール（CodeRabbit・Codex など）にコネクタで頼み、結果を待って評価・対応する。再レビューを頼むかの判断と依頼もここ |

## 設定（userConfig）

| キー | 既定 | 使いどころ |
|---|---|---|
| `review_tools` | 空 | リポの CLAUDE.md / AGENTS.md に `review-bots:` 行が無いときに使うレビューツール（カンマ区切り。例: `coderabbit,codex`）。どちらも無ければ `pr-review-triage` がユーザーに聞く |
| `rereview_threshold` | 3 | 重い指摘（Critical・P1 相当）をこの件数以上直したときだけ再レビューを頼む |

使えるツールの id は `skills/pr-review-triage/references/tools/` のファイル名（`codex`・`coderabbit`・`copilot`・`gemini`・`cursor-bugbot`）。

## コマンド

- `/review:dev-process:review-and-fix` — AI レビュー → 評価 → 修正計画 → 実装までを一続きで行う

## 他のプラグインとの関係

- スコープ外の気づきの処分は [workflow](../workflow/README.md) の `issue-ops` の判定表を参照する。無くても review 単体で使える
- `pr-review-triage` は workflow の `dev-flow` の 5・6 段（レビューを頼む・待つ・評価して直す・再レビュー）にあたる。workflow が無くても単体で使える
- 自動マージのリポは、リポの `.claude/dev-flow.json`（`{"autoMerge": true}`）で決める（workflow の `dev-flow` と同じファイル）
- GitHub の操作は GitHub コネクタが第一。`gh` はコネクタで取れないもの（ローカルの Monitor など）にだけ使う

## 前提

macOS / Linux、`python3`、`git`、`gh`、`jq`

## テスト

```bash
bash plugins/review/tests/run-all.sh
```
