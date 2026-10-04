---
name: pr-rereview
description: GitHub PR に、そのリポのレビュー bot（CodeRabbit・Codex・Copilot・Gemini・Cursor Bugbot など）への再レビュー依頼を投稿する。ユーザーの明示指示があったとき、または pr-review-wait の再レビュー基準（対応した指摘に Critical/P1 級が 3 件以上）を満たしたときに使う。例外として guards プラグインの設定 merge_allowed_repos に書いたリポで、エージェントが作った PR はエージェント判断で自律投稿してよい。
last_reviewed: 2026-09-21
review_after: 2027-03-20
---

# pr-rereview Skill

GitHub PR に、**そのリポでレビューしている bot への再レビュー依頼を投稿** するための Skill。どの bot がいるか・bot ごとの頼み方は `pr-review-wait` の `scripts/detect-bots.sh` と `references/bots.md` が正典。

## 使い方

ユーザーの明示指示があったとき、または `pr-review-wait` の再レビュー基準（対応した指摘に Critical/P1 級が 3 件以上）を満たしたときに実行する。基準の正典は `pr-review-wait`。

## merge_allowed_repos のリポの例外（2026-07-29 承認）

**guards プラグインの設定 `merge_allowed_repos`（hooks では環境変数 `CLAUDE_PLUGIN_OPTION_MERGE_ALLOWED_REPOS`、カンマ区切り、既定は空）に書いたリポで、エージェント（委譲先のセッション等）が作った PR に限り、上の基準を満たさなくても
エージェントの判断でユーザー確認なしに投稿してよい**（そのリポではマージ自体をユーザー以外の判断で認めているので、その前段の再レビュー投稿も同じ扱いにする）。

**例外の範囲外（＝「使い方」の条件どおり、明示指示か基準充足が必要）**:
- client / product リポジトリの PR（他組織リポを含む）
- merge_allowed_repos のリポでも、エージェントが作ったものでない PR
- 破壊的変更・後戻りしづらい変更を含む PR

判断ヒューリスティック（自律投稿するかの目安）は、そのリポの CLAUDE.md に定めがあればそれに従う。無ければ次の目安:
**クリティカル/actionable な指摘（nit・style は除外）が多い or PR のファイル数が多いときは再レビュー側に倒す**。
総コメント数では測らない（bot は nit を無限に出すのでキリがない）。

```text
/pr-rereview                # 現在ブランチの open PR を自動検出して投稿
/pr-rereview 59             # PR #59 に投稿
/pr-rereview 59 codex       # Codex のみ
/pr-rereview 59 coderabbit,copilot  # 複数をカンマ区切りで
/pr-rereview 59 all "for transaction correctness"  # Codex のレビュー focus を指定
```

対象は **そのリポで検出した bot**（`detect-bots.sh`。0 件なら投稿しない）。

## 実装方針

1. **PR 番号の決定**:
   - 引数で PR 番号が指定されていればそれを使う
   - 指定されていなければ `gh pr view --json number` で現在ブランチの open PR を検出
   - 検出できない (open PR がない / ブランチが remote にない) 場合はユーザーに確認

2. **対象 bot の決定** (引数 2 番目):
   - 省略 / `all`: そのリポで検出した bot すべて（`pr-review-wait/scripts/detect-bots.sh`）
   - `coderabbit` / `codex` / `copilot` / `gemini` / `cursor`（カンマ区切りで複数可）: その bot だけ

   頼み方は bot ごとに違う（コメントで頼むもの・レビュアーに指定するもの）。表は `pr-review-wait/references/bots.md`。コメントで頼む bot は 1 つのコメントにまとめて投稿する。

3. **Codex の focus 指定** (引数 3 番目以降):
   - 文字列があれば `@codex review <文字列>` の形で投稿
   - 例: `@codex review for transaction correctness`

4. **コメント投稿**:
   - `gh api "repos/{owner}/{repo}/issues/{number}/comments" -X POST -f body="..."` で投稿
   - リポジトリは `gh pr view <PR>` から取得 (or 現在ブランチの origin から)

5. **投稿後の確認メッセージ**:
   - 投稿された html_url を返す

6. **レビュー到着監視の起動**:
   - 投稿した時点で `pr-review-wait` skill の起動条件（「pr-rereview で再レビューを投げた直後」）を満たしている。
     **投稿後はそのまま到着監視（Monitor, persistent）を起動する**のが既定
   - 監視しないのは、ユーザーが「投げるだけでいい」「監視不要」と明示した場合のみ

## ⚠️ 投稿本文に長い focus 文を付けない（2026-07-29 実測）

**`@codex review` の後ろに長い日本語の focus 文を付けると、bot が反応しないことがある。**

実測（過去の実例・同一 PR・同一 commit に対して）:

| 投稿本文 | Codex の反応 |
|---|---|
| `@coderabbitai review` ＋ `@codex review`（素） | **4分で返答**（1回目） |
| `@codex review <日本語の焦点説明 200字超>` | **85分たっても無反応**（2回目） |
| `@coderabbitai review` ＋ `@codex review`（素・再投稿） | **4分で返答**（3回目・P2 を1件検出） |

素に戻した瞬間に返ってきたので、**長い focus 文がトリガーを潰していた**と判断できる（別の commit を挟んでいないので commit 差ではない）。

**規約**: 本文は `@coderabbitai review` / `@codex review` のメンション行にし、Codex に付けてよいのは**短い英語の focus まで**。
長い説明や日本語の焦点は**別コメントに分けて**書く（bot をメンションしない説明コメントを先に置き、その次にメンションだけのコメントを投稿する）。
SKILL の実装スクリプトが受け取る `<codex_focus>` 引数も、短い英語フレーズ（例: `for transaction correctness`）に留める。

## やってはいけないこと (anti-patterns)

- ❌ 再レビュー基準（Critical/P1 級 3 件以上）を満たさないまま、`push` / `commit` のたびに自動投稿
- ❌ 条件外の投稿とセットで監視ループまで起動する（禁止なのは*条件外の投稿*。
  条件を満たして投稿した後の監視起動はむしろ既定＝実装方針 6）
- ❌ 「念のため」「CLAUDE.md の自律ワークフロー」を理由に、条件を満たさないまま投稿（上の**merge_allowed_repos の例外に該当する場合を除く**）
- ❌ merge_allowed_repos の例外を、そこに書かれていないリポやエージェントが作ったものでない PR へ拡大解釈する
- ❌ 数分待っても来ないからもう一回投稿、というスパム的繰り返し
- ❌ PR が closed/merged の状態で投稿

## なぜ条件を絞るか

- bot のレビューは時間とコストがかかる（どれも LLM 駆動。従量課金の bot もある）
- 1 PR に複数回レビュー要請すると bot が「同じ commit を何度もレビューするか?」と混乱する
- 再レビューに値するのは重い指摘をまとめて直した後。push の度に投げると 1 PR で 5 巡になりコスト過大（過去の実例で実測）
- 条件を曖昧にすると `pr-review-wait` からの拡大解釈で毎 push 投稿に戻りやすい

## 実装スクリプト

`scripts/post_rereview.sh [<PR番号>] [<bots>] [<codex_focus>]` を呼ぶ（中身はスクリプトが正典。ここに写さない）。

## ユーザーへの報告フォーマット

実行後は以下を出力:

```text
✅ 再レビュー依頼を投稿しました
- PR: <PR番号>
- 依頼先: <頼んだ bot>
- コメント URL: <html_url>
- 投稿本文:
  <投稿した文字列>

レビュー到着監視を起動しました（30秒間隔ポーリング）。届いたら全文を再取得して評価・報告します。
```

（監視を起動しなかった場合はその旨と理由を報告する）
