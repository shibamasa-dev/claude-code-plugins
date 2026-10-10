# Copilot（id: `copilot`）

| 項目 | 中身 |
|---|---|
| bot のアカウント名（login と完全一致） | `Copilot` / `copilot-pull-request-reviewer[bot]` |
| 起動のしかた | リポ・組織の設定次第で自動。こちらから頼むときはレビュアーに指定する（コネクタの `request_copilot_review`） |
| 完了の合図 | レビュー（COMMENTED） |
| 「指摘なし」の合図 | 記録なし |
| レート制限・上限の合図（未レビュー） | 記録なし |
| 待ち時間 | 記録なし |
| 重い指摘 | Critical・High 相当で数える（重大度の書き方はツールごとに違う） |
| 再レビューの頼み方 | `request_copilot_review`（コメントでは頼まない） |
| 手元で回すコマンド | なし |
