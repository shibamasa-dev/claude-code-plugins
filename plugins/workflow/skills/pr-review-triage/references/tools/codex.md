# Codex（id: `codex`）

| 項目 | 中身 |
|---|---|
| bot のアカウント名（login と完全一致） | `chatgpt-codex-connector[bot]` |
| 起動のしかた | 設定次第で PR 作成時に自動レビューする。自動レビューを止めたリポでは、コメント `@codex review` で頼む |
| 完了の合図 | レビュー（指摘つき） |
| 「指摘なし」の合図 | PR への 👍 リアクション（レビューには載らない）。👀 はレビュー中 |
| レート制限・上限の合図（未レビュー） | 利用上限のコメント（「usage limit」「couldn't run」） |
| 待ち時間 | 書かれていない。上限はこちらから頼んでも返らないので、ユーザーに解除を頼む |
| 重い指摘 | P1 |
| 再レビューの頼み方 | コメント `@codex review`（ほかのツールへの依頼と 1 コメントにまとめる）。focus を付けるなら短い英語だけ（下） |
| 手元で回すコマンド | `codex exec`（Codex CLI） |

## 注意

- **未確認: ラベルで自動レビューから外せるか**（`review-auto: on` の `review:light`）。外せなければ、軽い PR でも自動レビューを ON にしていれば Codex は走る
- **Codex は直ったスレッドを自動で resolve しない。** 直っていても未解決のまま残るので、`isResolved` で対応状況を判断しない（PR 本文の対応表が記録になる）。
- **focus は短い英語だけ**（2026-07-29 実測）。`@codex review` の後ろに長い日本語の focus 文を付けると反応しないことがある。同一 PR・同一 commit での実測:

| 投稿本文 | Codex の反応 |
|---|---|
| `@coderabbitai review` ＋ `@codex review`（素） | 4 分で返答（1 回目） |
| `@codex review <日本語の焦点説明 200 字超>` | 85 分たっても無反応（2 回目） |
| `@coderabbitai review` ＋ `@codex review`（素・再投稿） | 4 分で返答（3 回目・P2 を 1 件検出） |

  素に戻した瞬間に返ってきたので、長い focus 文がトリガーを潰していたと判断した（別の commit を挟んでいない）。付けてよいのは `@codex review for transaction correctness` のような短い英語まで。長い説明が要るなら、bot をメンションしない説明コメントを先に置き、その後にメンションだけのコメントを投稿する。
