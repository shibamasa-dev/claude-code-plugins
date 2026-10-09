# devtools

リポの立ち上げと道具づくりのスキルと、使用枠をファイルへ書き出す mod。

## スキル

| スキル | 使いどころ |
|---|---|
| `codebase-doctor` | リポに必要な基本（テスト・CI・lint・セキュリティの初期設定など）がそろっているかの点検 |
| `remote-setup` | claude.ai/code や Cowork のクラウド環境用のセットアップ scaffold を作る |

`codebase-doctor` のテスト設計の点検（Check 6b）は、[testing](../testing/README.md) の `testcase-generator` が持つ置き場の定義を読む。testing が入っていなければその点検は SKIP（点数から除外）にする。

## mod

| mod | 動き |
|---|---|
| `rate-limits` | 使用枠（5時間・週）を `/tmp/claude-<uid>/rate-limits.json` に書き出す。`<uid>` は `id -u`。週の残り枠を外のスクリプトが見張る用 |

出力は `{"five_hour": {"used_percentage": 17, "resets_at": 1791553800, "seen_at": 1791552278}, "seven_day": {...}}`（`resets_at`・`seen_at` は epoch 秒）。枠ごとに `resets_at` が大きい方、同じなら `used_percentage` が大きい方を残す（ベストエフォート。プロセス間のロックは無いので、並列セッションがほぼ同時に書くと一時的に古い値へ戻ることがあり、次に使用率が動いたときに直る）。値が変わらなければ書かない。出力先は本人専用（700）のディレクトリで、無ければ作る。リンク・他人所有・700 以外なら何も書かない。中で一時ファイルに書いて `mv -f` で置き換える（失敗したら書かない）。mod が動くのは Claude Code の CLI（`$.process` を使うため）。

テストは `hooks/rate-limits.test.ts`（`claude plugin test plugins/devtools`）。

## 前提

macOS / Linux、`python3`、`git`、`gh`
