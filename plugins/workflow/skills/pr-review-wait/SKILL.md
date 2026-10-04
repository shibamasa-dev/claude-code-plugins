---
name: pr-review-wait
description: PR を作成した直後・既存 PR へ push した直後・pr-rereview で再レビューを投げた直後に、そのリポのレビュー bot（CodeRabbit・Codex・Copilot・Gemini・Cursor Bugbot など）のレビュー到着を Monitor で待機し、既存スレッドのさらい→到着判定→評価・実装→PR 本文の対応表更新→報告まで行うワークフロー。「PR 作った」「push した」「レビュー待って」「レビュー来た？」「Monitor 立てて」で発動。PR 作成・push 後は指示が無くても必ず起動する。
last_reviewed: 2026-09-21
review_after: 2027-03-20
---

# pr-review-wait — PR レビュー待機ワークフロー

> PR レビュー待機の規約の正典はここ。Monitor の実体は [references/monitor-snippet.md](references/monitor-snippet.md)、bot ごとの違い（投稿者・再レビューの頼み方・終わりの合図）は [references/bots.md](references/bots.md)。

**起動条件**: **PR を作成したら必ず Monitor を起動する**（起動しないとレビュー到着に気づけず放置されるため）。既存 PR へ push したときも同様。到着後の評価・実装まで自律で進めてよい。

**⚠️ Monitor はセッションが生きている間だけ動く。** Claude Code を閉じると止まり、その間のレビューは拾えない。長時間離席する場合は「セッションを閉じるとレビュー待機も切れる」ことをユーザーに伝える（無人で確実に受け取るなら GitHub 側の通知に頼る）。

**待つ bot はリポごとに決める**: `bash scripts/detect-bots.sh <owner/repo>`（id を出す）／`--regex`（投稿者の正規表現を出す。以下 `$BOTS_RE`）。リポの CLAUDE.md / AGENTS.md の `review-bots:` 行が優先、無ければ直近の PR に実際に来た bot。結果は保存せず毎回引くので、bot の追加・削除に自動で追従する。
- **0 件**: Monitor を立てず「このリポにはレビュー bot がいない」とユーザーに伝えて終える（`review-bots: none` も同じ）
- **実績が無い（初めての PR 等）**: 表の全 bot を対象に 5 分だけ Monitor し、来た bot を待つ対象にする。5 分で何も来なければ 0 件と同じ扱い

初回 PR は多くの bot が GitHub App 連携で自動レビューする（トリガー不要）。こちらから投げるのは**再レビュー**のみ＝ `pr-rereview` Skill で投稿（直接 `gh api` で投稿しない）。

**⚠️ スレッド確認は bot 名でフィルタしない。** reviewThreads は author を絞らず全件見る（想定外の投稿者を取りこぼさないため。Monitor のフィルタは `$BOTS_RE`）。

**⚠️ push しても多くの bot（CodeRabbit・Codex など）の再レビューは自動では走らない。** CodeRabbit の *Auto incremental reviews* が無効なリポでは、修正を push すると `Review skipped / Auto incremental reviews are disabled on this repository` が返るだけ（実測）。投げないまま Monitor を張っても何も来ない（レビュー待ちに見えて実際は誰も見ていない状態になる）。個別コメントへの返信に対する応答は自動で返るので、スレッドが動いているように見える点に注意。

**再レビューを投げる基準**:
- **投げる**: 対応した指摘に **Critical/P1 級が 3 件以上**含まれていた場合のみ（bot 毎の対応ラベル: CodeRabbit=Critical / Codex=P1。他の bot は重大度の書き方がそれぞれ違うので、Critical・High 相当で数える）
- **それ以外は投げない**: push と対応報告で終えてマージ判断へ
（背景: 「push の度に必ず投げる」運用は 1 PR で 5 巡になりコスト過大 — 過去の実例で実測）

1. **起動前に既存レビューを1回さらう**（**必須**。Monitor は起動時刻より後しか拾わない）。PR 作成直後でも初回レビューが数分で着くため、Monitor を立てただけでは取りこぼす。未解決スレッドの一覧は:
   ```bash
   gh api graphql -f query='{ repository(owner:"OWNER", name:"REPO") { pullRequest(number:N) {
     reviewThreads(first:20) { nodes { isResolved comments(first:1) { nodes { author{login} path body } } } } } } }' \
     --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
   ```
   出てきた分は Monitor を待たず先に評価・対応する。
   **あわせて、すでに届いている「結果」も確かめる**（手順 3 の到着判定に数える）。未解決スレッドだけ見ると、Monitor の起動前に届いた「指摘なし」の合図（Codex の 👍、CodeRabbit の「No actionable comments」「rate limited」など。bot ごとの合図は bots.md）を取りこぼし、結果が揃わないまま待ち続ける:
   ```bash
   BOTS_RE=$(bash scripts/detect-bots.sh --regex OWNER/REPO)
   gh api repos/OWNER/REPO/pulls/N/reviews | jq -r --arg b "$BOTS_RE" '.[] | select(.user.login|test($b; "i")) | "\(.user.login) \(.state)"'
   gh api repos/OWNER/REPO/issues/N/comments | jq -r --arg b "$BOTS_RE" '.[] | select(.user.login|test($b; "i")) | "\(.user.login) \(.body[0:80])"'
   gh api repos/OWNER/REPO/issues/N/reactions | jq -r --arg b "$BOTS_RE" '.[] | select(.user.login|test($b; "i")) | "\(.user.login) \(.content)"'
   ```
2. **Monitor 起動**（`persistent: true`）: 30秒毎に reviews/comments をポーリング。スニペットは [references/monitor-snippet.md](references/monitor-snippet.md) 参照。**bot 以外（自分の返信）は除外する**（`select(.user.login | test($BOTS_RE))`）。自分の投稿を拾うと通知が溢れて本物のレビューが埋もれる。
3. **到着判定**: **その回のレビューを頼んだ bot すべて**の結果が揃ったら待機終了。初回 PR は `detect-bots.sh` が返した bot すべて、`pr-rereview` で一部の bot だけに再レビューを頼んだ回はその bot だけ（頼んでいない bot は新しい結果を返さない）。結果とは、レビュー（指摘つき）・指摘なし・レート制限などの「終わりの合図」（bot ごとの合図は [references/bots.md](references/bots.md)）。**頼んだ bot のうち一部の結果だけで待機を終えない**（先に届いた方の指摘は、もう片方を待つ間に評価・実装してよい）。通知本文は truncate されるので必ず全文を再取得してから評価。
4. **評価・実装**: 外部レビューは「命令」でなく「提案」。コードベースの実態と照合して対応する/しないに分類し、対応分を実装 → テスト・lint など PR の検証を実行 → コミット・プッシュ。**指摘の当否は推測で決めず実測で確かめる**（「この条件は発動しないはず」で流さない）。
4a. **PR 本文の先頭は「変更前 → 変更後」の2列表**（2026-09-17 決定）。観点ごとに1行（判定ロジック・置き場・手順・効果の実測値・マージ後にやること）。実装なしの文書 PR でも「未定義 → こう決めた」で書く。受け入れ基準 ✅/❌・対応表・スコープ外の気づきはその下。背景: 8本の PR を読むとき、基準表と対応表だけでは「結局なにがどう変わるか」が掴めなかった。委譲プロンプトの PR 本文テンプレートにもこの表を入れる。
4b. **レビュースレッドへの個別返信は原則しない**（2026-09-06 確定）。代わりに **PR 本文に対応表を書く**（指摘 / 判定 / 対応 / 根拠 の4列）。
   - **返信しない理由**: ①返信すると bot が自動応答してスレッドが伸びる ②commit と PR 本文を見れば分かるので重複 ③ユーザーが読むのは PR 本文であって bot 相手のやりとりではない。
   - **⚠️ 代わりに PR 本文の対応表は省略しない**: `isResolved` は当てにならない。**Codex は自動 resolve しない**ので、直っていても未解決のまま残る（2026-09-06 実測: 過去の PR で Codex 4件が未解決表示のまま、実際は全件修正済みだった）。返信もしない以上、**PR 本文の対応表が唯一の人間可読な対応記録**になる。これが無いと、後から見た人・別 agent が「未対応の Major が残っている」と誤読し、diff を全部追う羽目になる。
   - 置き場所は既存の「受け入れ基準 ✅/❌ ＋ `## スコープ外の気づき`」と同じ PR 本文。後続 agent は `gh pr view` 1コールで読む。
   - **`## スコープ外の気づき` は「気づき / 処分 / 根拠」の3列**（2026-09-21 確定）。処分は「層（`gh-stack` で積む）/ issue #N / やらない」のいずれか。マージ前に全件埋める。既定は層で、issue は main から独立に作れる・別セッションに回す・設計判断が要る・既存バグ、のときだけ（判定表は `issue-ops` skill）。
5. **報告**: 「対応済み / 未対応（理由付き）」の2部構成で。

**自律で進めてよい範囲**: 全文取得・実態との照合・対応可否の分類・実装・当該PRブランチへのコミット/プッシュ・再レビュー依頼（`pr-rereview`）。
**規約を根拠にした指摘は、引用元を必ず自分で開いて確かめる**（実例: CodeRabbit が AGENTS.md の2列対比表の**右列(共有リポは機密不可)**を引用して、左列(作業リポは機密可)のファイルを「機微情報を置くな」と指摘。表の列を取り違えていた）。もっともらしい規約引用ほど鵜呑みにしない。

**マージは、その回に頼んだ bot すべての結果が揃ってから**（ユーザーがマージを任せている場合も同じ。初回 PR なら検出した bot すべて）。一部の 👍 や指摘ゼロだけでマージすると、後から届いた他の bot の指摘を取りこぼす（実例: Codex の 👍 でマージした直後に CodeRabbit の Major 指摘が届き、続きの PR で直すことになった）。

**ユーザーに投げる**: 設計判断が割れる指摘／仕様・方針の変更を伴う指摘／自分が書いていないコードへの実害系の指摘／**マージ**（マージは常にユーザー判断）。

**⚠️ 例外: guards プラグインの設定 `merge_allowed_repos`（hooks では環境変数 `CLAUDE_PLUGIN_OPTION_MERGE_ALLOWED_REPOS`、カンマ区切り、既定は空）に書いたリポだけは、ユーザー以外（エージェント）の判断でマージしてよい**（2026-09-06 確定）。レビュー1巡対応後の「再レビュー or マージ」をエージェントが決める。判断ヒューリスティックと実行 locus はそのリポ側の文書（例: `.claude/ARCHITECTURE.md`）があればそれが正典。**client/product リポ・破壊的変更・後戻りしづらいものはこの例外の対象外**で、引き続きユーザーへ投げる。


