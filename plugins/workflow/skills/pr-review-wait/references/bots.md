# レビュー bot の一覧

`scripts/detect-bots.sh` が判定に使う表。ここに無い bot は検出しない（足すときは表とスクリプトの `BOTS` を両方直す）。

| id | 投稿者（login と完全一致・bot アカウントのみ） | 初回レビュー | 再レビューの頼み方 | 「終わった」の合図 | 「未レビュー」の合図（待ち直す） |
|---|---|---|---|---|---|
| `coderabbit` | `coderabbitai[bot]` | PR 作成で自動 | コメント `@coderabbitai review` | レビュー（指摘つき）／ walkthrough に「No actionable comments」 | 「rate limited」（待ち時間が書かれる）／「plan limit reached」 |
| `codex` | `chatgpt-codex-connector[bot]` | PR 作成で自動（設定次第） | コメント `@codex review` | レビュー（指摘つき）／ PR への 👍 リアクション（👀 はレビュー中） | 利用上限のコメント（「usage limit」「couldn't run」） |
| `copilot` | `Copilot` / `copilot-pull-request-reviewer[bot]` | リポ・組織の設定次第 | `gh pr edit <N> --add-reviewer @copilot` | レビュー（COMMENTED） | — |
| `gemini` | `gemini-code-assist[bot]` | PR 作成で自動 | コメント `/gemini review` | レビュー（COMMENTED） | — |
| `cursor` | `cursor[bot]` | PR 作成で自動（従量課金に注意） | コメント `bugbot run` | レビュー（指摘つき・指摘なし） | 上限到達のコメント |

**「未レビュー」の合図は「終わった」に数えない**（2026-10-06 ユーザー決定）。レート制限・プランや利用の上限は、bot が何も見ていないという知らせ。これを「指摘なし」と同じに数えて待機を終えると、誰もレビューしていない PR を「マージ判断に回せる」と報告してしまう（実例: CodeRabbit が rate limited の段階でマージを依頼し、その後に届いた指摘の 1 件が支払額に関わる設計判断だった）。

**投稿者は完全一致で見る**。部分一致（例: `codex` を含む）にすると、人間のアカウントの投稿を bot のレビューとして拾い、その内容に従ってしまう余地ができる。

## 判定のしかた（記憶しない）

- リポの CLAUDE.md（または AGENTS.md）に `review-bots: coderabbit, codex` の行があれば、それだけを使う（`review-bots: none` で「bot なし」）
- 無ければ、そのリポの直近の PR（既定 5 件。外した bot を引きずらないよう少なめ）のレビュー・レビューコメント・コメント・リアクションの投稿者から、上の表の bot を拾う。上限・レート制限の通知コメントも「入っている」印に数える（その bot を待つ対象に入れ、「未レビュー」として扱うため）
- どちらも結果を保存しない。毎回 GitHub から引くので、bot を足す・外すと次の PR から自動で追従する
- 過去の PR が無い（初めての PR）・判定できないときは空を返す。呼び出し側は「数分だけ様子を見て、来た bot を待つ」に倒す
