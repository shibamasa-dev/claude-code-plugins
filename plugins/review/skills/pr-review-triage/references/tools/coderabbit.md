# CodeRabbit（id: `coderabbit`）

| 項目 | 中身 |
|---|---|
| bot のアカウント名（login と完全一致） | `coderabbitai[bot]` |
| 起動のしかた | GitHub App の設定で PR 作成時に自動レビューする。自動レビューを止めたリポでは、コメント `@coderabbitai review` で頼む |
| 完了の合図 | レビュー（指摘つき） |
| 「指摘なし」の合図 | walkthrough（自動サマリのコメント）に「No actionable comments」。指摘ゼロのときはレビューを作らず、完了をこの walkthrough の中に書くだけ |
| レート制限・上限の合図（未レビュー） | 「rate limited」（待ち時間が書かれる）／「plan limit reached」 |
| 待ち時間 | rate limited はコメントに書かれた時間。plan limit はこちらから頼んでも返らないので、ユーザーに解除を頼む。オンデマンドレビューのチェックボックスはユーザーが押す |
| 重い指摘 | Critical |
| 再レビューの頼み方 | コメント `@coderabbitai review`（ほかのツールへの依頼と 1 コメントにまとめる） |
| 手元で回すコマンド | なし |

## 注意

- **push しても再レビューは自動では走らない。** *Auto incremental reviews* が無効なリポでは、修正を push すると `Review skipped / Auto incremental reviews are disabled on this repository` が返るだけ（実測）。頼まないまま待っても何も来ない。
- walkthrough は push のたびに更新されるので、Monitor では本文を通知せず、「No actionable comments」と未レビューの合図だけを状態行として出す（`../monitor-snippet.md`）。未レビューの合図は walkthrough とは別のコメントで来ることもある。
- **未検証**: 自動レビューを止めた状態で手動依頼し指摘ゼロのとき walkthrough に『No actionable comments』が出るか。最初の heavy PR で確かめて追記する。
