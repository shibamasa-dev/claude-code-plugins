# review

PR のレビューを回すスキルとコマンド。依頼からマージまでの開発フロー（`dev-flow`）は [workflow](../workflow/README.md) にある。

## スキル

| スキル | 使いどころ |
|---|---|
| `pr-review-triage` | PR を出した直後や push の後に、差分の重さでレビューの頼み先を振り分ける。軽い PR（文書だけ・200 行以内）は Claude がレビューして PR 本文に書き、CI だけ待つ。重い PR はレビューツール（CodeRabbit・Codex など）にコネクタで頼み（ツールの自動レビューを ON にしたリポでは頼まずに、軽い PR だけ `review:light` ラベルで自動レビューから外す）、結果を待って評価・対応する。再レビューを頼むかの判断と依頼もここ |

## 設定（userConfig）

| キー | 既定 | 使いどころ |
|---|---|---|
| `review_heavy` | 空 | 重い PR に使うレビューツール（カンマ区切り。例: `coderabbit,codex`。`none` はツールなし）。リポの行も設定も無ければ `pr-review-triage` がユーザーに聞く |
| `review_light` | `claude` | 軽い PR に使うもの。`claude` なら Claude がレビューする。ツールの id を書けば軽い PR も重い PR と同じ扱い（ラベルを付けない） |
| `review_auto` | `off` | ツールの自動レビューが ON か（`on` / `off`）。下の「自動レビューを ON のまま使う」 |
| `rereview_threshold` | 3 | 重い指摘（Critical・P1 相当）をこの件数以上直したときだけ再レビューを頼む |

使えるツールの id は `skills/pr-review-triage/references/tools/` のファイル名（`codex`・`coderabbit`・`copilot`・`gemini`・`cursor-bugbot`）。

リポごとに変えるなら、リポの CLAUDE.md（または AGENTS.md）に行で書く。行が userConfig より優先する。`review-notes:` は重点的に見てほしいことを自然言語で書く行で、依頼文と Claude のレビューに渡す（振り分けの判定には使わない）:

```
review-heavy: coderabbit, codex
review-light: claude
review-auto: on
review-notes: 権限まわりの変更は特に見てほしい
```

### 自動レビューを ON のまま使う（`review-auto: on`）

ツールの自動レビューを ON のままにして、軽い PR だけラベルで外す。手動の `@coderabbitai review` も CodeRabbit の上限に 1 回ずつ数えられるので、自動レビューを止めても枠は節約できない。CodeRabbit は自動レビューの制御（ラベルなど）で外した PR を上限に数えない（[rate limits](https://docs.coderabbit.ai/management/rate-limits)）。

- 軽い PR（`review-light: claude` のとき）は、PR を作る前に判定して `review:light` ラベルを付けて作る。Claude がレビューする
- 重い PR はツールが自動で走るので、依頼のコメントは投稿せず結果を待つ
- push で軽い → 重いに変わったら、ラベルを外してツールに手動で頼む
- `review-light: coderabbit, codex` のようにツールを書くと、軽い PR にもラベルを付けず、重い PR と同じ扱いになる（ラベルの運用をやめるときの戻し方）

ツール側には、ラベルの付いた PR を自動レビューから外す設定を入れる。CodeRabbit ならリポの `.coderabbit.yaml` に:

```yaml
reviews:
  auto_review:
    labels: ["!review:light"]
```

`!` で始まるラベルは否定の一致（[configuration](https://docs.coderabbit.ai/reference/configuration)）。

**未確認**（実測していない）:
1. PR を作るときに付けたラベルで、CodeRabbit が最初の自動レビューの前に外すか
2. この設定を組織単位で入れられるか（入れられなければリポごとの `.coderabbit.yaml`）
3. Codex をラベルで自動レビューから外せるか（外せなければ軽い PR でも Codex は走る）

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
