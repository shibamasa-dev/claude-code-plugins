# レビュー bot の一覧

`scripts/detect-bots.sh` が判定に使う表。ここに無い bot は検出しない（足すときは表とスクリプトの `BOTS` を両方直す）。

| id | 投稿者（login と完全一致・bot アカウントのみ） | 初回レビュー | 再レビューの頼み方 | 「終わった」の合図 |
|---|---|---|---|---|
| `coderabbit` | `coderabbitai[bot]` | PR 作成で自動 | コメント `@coderabbitai review` | レビュー（指摘つき）／ walkthrough に「No actionable comments」／「rate limited」 |
| `codex` | `chatgpt-codex-connector[bot]` | PR 作成で自動（設定次第） | コメント `@codex review` | レビュー（指摘つき）／ PR への 👍 リアクション（👀 はレビュー中） |
| `copilot` | `Copilot` / `copilot-pull-request-reviewer[bot]` | リポ・組織の設定次第 | `gh pr edit <N> --add-reviewer @copilot` | レビュー（COMMENTED） |
| `gemini` | `gemini-code-assist[bot]` | PR 作成で自動 | コメント `/gemini review` | レビュー（COMMENTED） |
| `cursor` | `cursor[bot]` | PR 作成で自動（従量課金に注意） | コメント `bugbot run` | レビュー／コメント（上限到達のコメントも「終わり」） |

**投稿者は完全一致で見る**。部分一致（例: `codex` を含む）にすると、人間のアカウントの投稿を bot のレビューとして拾い、その内容に従ってしまう余地ができる。

## 判定のしかた（記憶しない）

- リポの CLAUDE.md（または AGENTS.md）に `review-bots: coderabbit, codex` の行があれば、それだけを使う（`review-bots: none` で「bot なし」）
- 無ければ、そのリポの直近の PR（既定 5 件。外した bot を引きずらないよう少なめ）のレビュー・レビューコメント・コメント・リアクションの投稿者から、上の表の bot を拾う
- どちらも結果を保存しない。毎回 GitHub から引くので、bot を足す・外すと次の PR から自動で追従する
- 過去の PR が無い（初めての PR）・判定できないときは空を返す。呼び出し側は「数分だけ様子を見て、来た bot を待つ」に倒す
