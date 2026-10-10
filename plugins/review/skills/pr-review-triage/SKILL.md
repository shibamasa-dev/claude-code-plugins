---
name: pr-review-triage
description: PR を作成した直後・既存 PR へ push した直後に、差分の重さでレビューの頼み先を振り分け、頼む→待つ→評価して直す→再レビューまでを回すワークフロー。軽い PR（README などの文書だけ・200 行以内）は Claude が code-review skill でレビューして PR 本文に記録し CI だけ待つ。重い PR（コード・設定・skills/hooks などの振る舞いを決める文書・200 行超）はそのリポのレビューツール（CodeRabbit・Codex・Copilot・Gemini・Cursor Bugbot など）にコネクタで頼み（ツールの自動レビューを ON にしたリポでは頼まずに、軽い PR だけ `review:light` ラベルで自動レビューから外す）、結果を待って評価・対応し、PR 本文に対応表を書く。再レビュー（指摘対応後にもう一度頼む）を投げるかの判断と依頼もここ。「PR 作った」「push した」「レビューして」「レビュー待って」「レビュー来た？」「再レビュー投げて」「重めでレビューして」、英語の "PR created", "opened a PR", "pushed", "review", "re-review", "request review" で発動。PR 作成・push 後は指示が無くても必ず起動する。
last_reviewed: 2026-10-10
review_after: 2027-04-10
---

# pr-review-triage — PR のレビューを重さで振り分けて回す

> workflow プラグインの dev-flow の 5・6 段（頼む・待つ・評価して直す・再レビュー）の正典。ツールごとの違い（アカウント名・頼み方・完了と未レビューの合図）は [references/tools/](references/tools/) に 1 ツール 1 ファイル、ローカルで待つ Monitor の実体は [references/monitor-snippet.md](references/monitor-snippet.md)。

**前提**: ツールの自動レビューの扱いはリポごとに 2 通りある（`review-auto:`。1 で決める）。
- **`off`（既定）**: ツールの自動レビューは止めてある。自動のままだと README の 1 行修正でもツールが走り、プランの上限（1 時間あたりの回数）を軽い PR が食い潰す。止めた代わりに、PR ごとにここで頼み先を決めて頼む
- **`on`**: ツールの自動レビューは ON のまま。軽い PR だけ、作るときに `review:light` ラベルを付けてツール側の設定で自動レビューから外す（2.1）。重い PR は自動で走るので頼まない。手動の `@coderabbitai review` も上限に 1 回ずつ数えられるので、止めても枠は節約できない。CodeRabbit はラベルなどで自動レビューから外した PR を上限に数えない（[rate limits](https://docs.coderabbit.ai/management/rate-limits)）

**起動するとき**: PR を作った直後（workflow の dev-flow-gate の案内）、既存 PR へ push した直後（再レビューを頼むかを 6 の基準で決める）、ユーザーが再レビューを明示で頼んだとき、レート制限が明けたとき。

**待ち方はクラウドとローカルで違う**: クラウドのセッションは PR イベントの購読（`subscribe_pr_activity`）でターンを終える。ローカルは Monitor を立てる。Monitor はシェルのコマンドを回す仕組みなので、中では `gh` を使う（コネクタを使えない、CLI が残る例外）。**Monitor はセッションが生きている間だけ動く。** 長時間離席するなら「セッションを閉じるとレビュー待機も切れる」とユーザーに伝える。

## 1. 使うツールを決める

```bash
export CLAUDE_PLUGIN_OPTION_REVIEW_HEAVY='${user_config.review_heavy}' CLAUDE_PLUGIN_OPTION_REVIEW_LIGHT='${user_config.review_light}' CLAUDE_PLUGIN_OPTION_REVIEW_AUTO='${user_config.review_auto}'
D=${CLAUDE_PLUGIN_ROOT}/skills/pr-review-triage/scripts/detect-bots.sh
bash $D          # heavy の PR に使うツール
bash $D --light  # light の PR に使うもの（claude か ツールの id）
bash $D --auto   # ツールの自動レビュー（on / off）
```

以降の節の `$D` はこのパス（別のシェルで回すときは環境変数と一緒に定義し直す）。

リポの作業ツリーの中で実行する。キーごとに、上から最初に見つかったものを使う（結果は保存しない）:

1. リポの CLAUDE.md（または AGENTS.md）の行
2. userConfig

| 行 | userConfig | 例 | 意味 |
|---|---|---|---|
| `review-heavy:` | `review_heavy` | `coderabbit, codex` | heavy の PR に使うツール（カンマ区切り）。`none` は「ツールなし」 |
| `review-light:` | `review_light` | `claude` | light の PR に使うもの。既定は `claude`（3 の手順で Claude がレビュー）。ツールの id を書けば light も heavy と同じ扱い（ラベルを付けず、そのツールで 4 の手順） |
| `review-auto:` | `review_auto` | `on` / `off` | ツールの自動レビューが ON か。既定は `off` |
| `review-notes:` | — | 自然言語 | 重点的に見てほしいこと。行をそのまま読む（スクリプトは読まない） |

- **id が出る**: その回に頼むツール。id は `references/tools/<id>.md` のファイル名
- **何も出ずに exit 0**（`review-heavy: none`）: ツールのいないリポ。heavy でも 3 の手順で Claude がレビューする（`review-light: none` も同じく 3 の手順）
- **exit 4**（`review-heavy:` の行も設定も無い）: どのツールを使うかをユーザーに聞き、リポの CLAUDE.md に `review-heavy:` 行を足す PR を提案する
- **exit 5**（行か設定はあるが読めない。知っている id が 1 つも無い綴り違い、`review-auto:` が `on` / `off` 以外、`review-light:` で `claude` とツールの id を並べた（`claude` はほかの id と並べられない））: 「ツールなし」「off」とは扱わない。stderr をユーザーに見せて、どのつもりかを聞く（`none` の書き間違いで誰もレビューしない PR が出るのを防ぐ）

**`review-notes:`** は振り分け（2）の判定には使わない。渡し先は 2 つ:
- Claude のレビュー（3）: `code-review` に重点として渡す
- ツールへの依頼（4.1）: 依頼コメントのメンション行には混ぜない。メンションの無い説明コメントとして依頼コメントの前に投稿する（Codex は長い focus 文で反応しなくなる。`references/tools/codex.md`）。`review-auto: on` で依頼しない回は渡す先が無いので、ツールに常に伝えたいことはツール側の設定に書く

**過去の PR に来た bot から推測しない。** 自動レビューを止めると軽い PR が bot の痕跡を残さないので、推測は空になり、誰もレビューしない PR が出る。

## 2. 振り分ける

```bash
git fetch origin <base>
git diff --numstat origin/<base>...HEAD | bash ${CLAUDE_PLUGIN_ROOT}/skills/pr-review-triage/scripts/classify.sh
```

入力は手元の差分（`gh` は使わない。クラウドでも手元に clone がある）。1 行目が `light` / `heavy`、2 行目以降が理由。判定は決定的で、同じ差分なら同じ結果になる。

**heavy**（どれか 1 つでも当たれば heavy。迷ったら heavy に倒す。見逃しの方がツール 1 回分より高くつく）:
- 文章ファイル（`.md` `.markdown` `.txt` `.rst` `.adoc`）以外を含む。拡張子の無いファイル（`.gitignore` など）とバイナリも含む
- パスに `skills/` `hooks/` `agents/` `commands/` `rules/` `.github/` がある文章、またはファイル名が `SKILL.md` `CLAUDE.md` `AGENTS.md`。プラグインのリポではこれらの md が中身そのもので、1 行の変更でエージェントの動作が変わる
- 変更行数（追加＋削除）の合計が 200 行を超える。一度に読んで指摘の精度が落ちない量の目安
- 差分が空（取得に失敗した可能性がある）

**light**: それ以外（README などの文書だけで、200 行以内）。

light でも、ユーザーが「重めでレビューして」と頼んだら heavy の手順（4）で回す（重い方へ倒すのはよい。軽い方へは倒さない）。`review:light` ラベルが付いていれば外してから頼む（5 と同じ）。

基準を変えたら `bash ${CLAUDE_PLUGIN_ROOT}/skills/pr-review-triage/evals/run_evals.sh` を回す（このリポの実 PR から取った差分で判定を確かめる。オフラインで動く）。fixture にはまだ light の実例が無い。**最初の light PR が出たら、そのマージの `git diff --numstat <merge>^1 <merge>` を fixture に足す**（合成した light ケースは作らない）。

### 2.1 `review-auto: on` のとき — PR を作る前にラベルを決める

`review-auto: on` のリポでは、ラベルを PR を作るときに付ける（作った後に付けても、ツールの最初の自動レビューに間に合わない可能性がある）。そのため 1・2 を **PR を作る前に** 回す（workflow の dev-flow の 4 段もここを指す）。

1. `bash $D --auto` が `on` で、2 の判定が `light`、かつ `bash $D --light` が `claude`（または何も出ない）のときだけ、`review:light` ラベルを付けて作る。それ以外はラベルを付けない
   - **`review-light:` にツールを書いたリポ**（例: `review-light: coderabbit, codex`）では、light でもラベルを付けない。ツールの自動レビューがそのまま走り、heavy と同じ扱いになる（4 の手順。待つツールは `bash $D --light` の id）。ラベルの運用をやめたいときの戻し方もこれ
2. ラベルはリポに無ければ先に作る: `gh label create review:light --force --description "light の PR。ツールの自動レビューから外す"`（`--force` は既にあっても上書きするだけ）
3. PR は `gh pr create --label review:light ...` で作る。GitHub コネクタの `create_pull_request` はラベルを渡せないので、ここは `gh` を使う例外
4. ツール側で、このラベルの PR を自動レビューから外す設定を入れておく。CodeRabbit の設定例と未確認の点は [references/tools/coderabbit.md](references/tools/coderabbit.md)。ラベルで外せないツールは light でも走る（Codex は未確認。`references/tools/codex.md`）

PR を作った後の流れ:
- **light（ラベルあり）**: 3 のまま
- **heavy**: ツールは自動で走るので、4.1 の依頼コメントは投稿しない。4.2〜4.4 はそのまま。4.4 の「4.1 で控えた head SHA と時刻」は、PR を作ったときの head SHA と時刻（`pull_request_read` の `get` の `head.sha` と `created_at`）に読み替える

## 3. light — Claude がレビューして CI だけ待つ

1. 組み込みの `code-review` skill を PR 番号つきで起動する（例: `code-review <PR番号>`。`review-notes:` があれば重点として添える）。`coderabbit:code-review` ではない（あちらは CodeRabbit の枠を使う）。`--comment` は付けない（スレッドに書かない運用のため）。`code-review` が無い環境では、general-purpose subagent に `git diff origin/<base>...HEAD` を渡してレビューさせる
2. 結果を **PR 本文** の `## レビュー（Claude）` 節に、対応表（指摘 / 判定 / 対応 / 根拠）で書く。**指摘ゼロでも節を置いて「指摘なし」と書く**（後から見た人が「レビューされていない」と誤読しないため）。本文の更新はコネクタの `update_pull_request`
3. 対応する指摘を直して push する。ツールには頼まない
4. **CI だけ待つ**: クラウドは `subscribe_pr_activity`、ローカルは Monitor で [references/monitor-snippet.md](references/monitor-snippet.md) の「CI だけ待つ」を回す。待たずに終えると dev-flow-gate の Stop の確認に止められる。チェックが 1 つも付かずに `NO_CHECKS` で抜けたら、CI が緑とは数えず「このリポ（この commit）にはチェックが無い」と報告する。取得の失敗が続いて `FETCH_GAVE_UP` で抜けたら、CI は「未確認」と報告し、取得し直して結果が出るまでマージの判断に進まない

`review-heavy: none` のリポで heavy だった PR も同じ手順で回し、`## レビュー（Claude）` に heavy だった理由（classify.sh の理由行）も書く。

## 4. heavy — ツールに頼む → 待つ → 評価して直す

### 4.1 頼む

`review-auto: on` のリポで PR を作った直後は頼まない（2.1）。それ以外の頼み方は `references/tools/<id>.md` の「再レビューの頼み方」（初回も同じ）。**頼む直前に、今の head SHA（`pull_request_read` の `get` の `head.sha`）と時刻を控える**（4.4 で前の回の結果と分けるため）。

- **コメントで頼むツール**は、コネクタの `add_issue_comment` で **1 コメントにまとめて**投稿する（例: `@coderabbitai review` と `@codex review` を 1 行ずつ）。本文はメンション行だけにする（focus の制約は各ツールのファイル。Codex は短い英語だけ）
- **Copilot** はコネクタの `request_copilot_review`
- スクリプトで `gh` から投稿しない

### 4.2 既存の結果を先にさらう

**必須。** Monitor・購読は起動した後の出来事しか拾わない。依頼より前に届いていた結果を取りこぼすと、結果が揃わないまま待ち続ける。

- 未解決スレッド: コネクタの `pull_request_read`（`get_review_comments`）。**投稿者で絞らない**（想定外の投稿者を取りこぼさないため。Monitor のフィルタだけがツールのアカウントで絞る）
- レビューとコメント: `pull_request_read`（`get_reviews`・`get_comments`）
- リアクション（Codex の 👍 など）: コネクタで取れないので `gh api repos/OWNER/REPO/issues/N/reactions`

出てきた指摘は待たずに先に評価・対応する。「指摘なし」の合図が届いていればそのツールは結果が揃ったに数える。レート制限・上限の合図なら、そのツールは**未レビュー**として 4.4 に回す。

### 4.3 待つ

- **クラウド**: `subscribe_pr_activity` で PR イベントを購読してターンを終える
- **ローカル**: Monitor（`persistent: true`）を立てる。実体は [references/monitor-snippet.md](references/monitor-snippet.md)。投稿者のフィルタは `bash $D --regex` の出力（1 と同じ環境変数を付ける。light をツールで回すときは `bash $D --light --regex`）。**ツール以外（自分の返信）は除外する**。自分の投稿を拾うと通知が溢れて本物のレビューが埋もれる

通知本文は truncate されるので、新着を検知したら必ず全文を取り直してから評価する。満了通知が 0 件でも「まだ来ていない」と読まず、一次ソースを引き直す。

### 4.4 到着判定

- **その回に頼んだツールすべて**の結果が揃ったら待機を終える。結果とは、レビュー（指摘つき）か「指摘なし」の合図（ツールごとの合図は `references/tools/<id>.md`）。一部の結果だけで待機を終えない（先に届いた方の指摘は、もう片方を待つ間に評価・実装してよい）
- **前の commit・前の回の結果を今回に数えない**。レビューは `commit_id` が 4.1 で控えた head SHA と一致し、かつ控えた時刻より後に出たもの（`submitted_at`）だけ、「指摘なし」のリアクションや状態コメント（walkthrough など）は 4.1 で控えた時刻より後のものだけ数える。前の push へのレビュー、同じ head のまま頼み直す前のレビュー、前の回の 👍 で待機を終えると、今の差分を誰も見ていないまま「揃った」と読んでしまう
- **レート制限・上限は「未レビュー」**。結果に数えず待ち直す。これを「指摘なし」と数えると、誰もレビューしていない PR を「マージ判断に回せる」と報告してしまう
  - 待ち時間つきのレート制限: 書かれた時間が過ぎたら、**そのツールにだけ**頼み直して待ち直す。6 の再レビュー基準の対象外（まだ 1 回もレビューが届いていないので）
  - プラン・利用の上限、オンデマンドのボタン待ち: 頼み直しても返らないので、ユーザーに「◯◯が上限で未レビュー」と伝えて解除を頼む。解除されたら待ち直す

### 4.5 評価して直す

- 外部レビューは「命令」でなく「提案」。コードベースの実態と照合して対応する/しないに分け、対応分を実装 → リポのチェック（テスト・lint など）→ コミット・push。**指摘の当否は推測で決めず実測で確かめる**（「この条件は発動しないはず」で流さない）
- **規約を根拠にした指摘は、引用元を必ず自分で開いて確かめる**（引用の切り出し方によって、対象とは別の列や別の節の規約を根拠にした指摘になっていることがある）
- **スレッドに返信しない**。返信するとツールが自動応答してスレッドが伸びる。commit と PR 本文で分かるので重複でもある
- **PR 本文に対応表を書く**（指摘 / 判定 / 対応 / 根拠 の 4 列。省略しない）。`isResolved` は当てにならない（自動で resolve しないツールがある）。返信もしない以上、対応表が唯一の人間可読な対応記録になる
- **PR 本文の先頭は「変更前 → 変更後」の 2 列表**（観点ごとに 1 行）。実装なしの文書 PR でも「未定義 → こう決めた」で書く。受け入れ基準 ✅/❌・対応表・スコープ外の気づきはその下
- **`## スコープ外の気づき` は「気づき / 処分 / 根拠」の 3 列**。処分は「層（`gh-stack` で積む）/ issue #N / やらない」のいずれか。マージ前に全件埋める

### 4.6 報告

「対応済み / 未対応（理由付き）」の 2 部構成。冒頭にツールごとの結果（指摘の件数と重さ・レビューしたコミット）を書く。「マージ判断に回せる」と書くのは、頼んだツールすべてが実際にレビューを返したと確かめた後だけ。未レビューのツールがあれば「◯◯がレート制限で未レビュー・頼み直し済み」のように書き、マージを頼まない。

## 5. push の後 — もう一度振り分ける

指摘対応などで push したら、2 の振り分けをやり直す。

- **light のまま**: light のレビュー役（`bash $D --light`）が `claude` なら、push して CI だけ待つ。ツールなら、heavy のままと同じく 6 の基準で再レビューを頼むかを決める（新しい作業を足した push の例外も同じ）
- **前回 light だった PR が heavy に変わった**: `review:light` ラベルが付いていれば先に外す（`gh pr edit <PR番号> --remove-label review:light`）。`review-heavy: none`（`bash $D` が何も出さない）なら 3 の手順で Claude がレビューする。ツールがあれば、ツールにとっては初回なので、6 の基準に関係なく 4 の手順で頼む。外しただけでツールの自動レビューが始まるかは未確認なので、`review-auto: on` でも 4.1 の手順で手動で頼む
- **heavy のまま**: 6 の基準で再レビューを頼むかを決める。レビューの結果が返った後に指摘への対応以外の新しい作業を足した push は、6 の基準の例外で頼む

## 6. 再レビュー

**頼む**: その回に直した指摘のうち、重い指摘（CodeRabbit=Critical / Codex=P1。ほかのツールは Critical・High 相当。ツールごとの呼び方は `references/tools/<id>.md` の「重い指摘」）が **${user_config.rereview_threshold} 件以上**（userConfig `rereview_threshold`。既定 3）あったときだけ、その回に頼んだツールへ頼む（頼み方は 4.1、そのあと 4.2 から）。

**それ以外は頼まない**: push して CI だけ待ち、マージ判断へ。push のたびに頼むと 1 PR で 5 巡になりコスト過大（過去の実例で実測）。多くのツールは push しても再レビューを自動では走らせないので、頼まずに待っても何も来ない。

`review-auto: on` のリポで、ツールの設定で push ごとに自動でレビューが走る（CodeRabbit の incremental review など）なら、そのツールには頼まず 4.2 から待つ（同じ push に二重に枠を使わないため）。

**基準の例外**（基準を満たさなくても頼んでよい）:
- **ユーザーの明示指示**（「再レビュー投げて」）
- **レビューの結果が返った後に、指摘への対応以外の新しい作業を足した push**。足した範囲はまだ誰も見ていないので、再レビューの基準に関係なく頼む。指摘への対応だけの push は従来の基準に従う。結果が返る前に足した分は初回のレビューに含まれる
- **レート制限明けの頼み直し**（4.4。そのツールにだけ）
- **自動マージのリポ**（リポの `.claude/dev-flow.json` が `{"autoMerge": true}`）で、**エージェント（委譲先のセッション等）が作った PR**。そのリポではマージ自体をユーザー以外の判断で認めているので、その前段の再レビューも同じ扱いにする。判断の目安はリポの CLAUDE.md に定めがあればそれ、無ければクリティカル/actionable な指摘（nit・style は除く）が多い、または PR のファイル数が多いときに頼む側へ倒す。総コメント数では測らない（ツールは nit を無限に出す）
  - 対象外（基準か明示指示が要る）: client / product リポ（他組織のリポを含む）の PR／エージェントが作ったものでない PR／破壊的変更・後戻りしづらい変更を含む PR

## マージ

- **マージ（とマージの依頼）は、その回に頼んだツールすべての結果が揃ってから**（ユーザーがマージを任せている場合も同じ）。レート制限・上限は結果に数えない。一部の 👍 や指摘ゼロだけでマージすると、後から届いた他のツールの指摘を取りこぼす（実例: 👍 でマージした直後に別のツールの Major 指摘が届き、続きの PR で直すことになった）
- **ユーザーに投げる**: 設計判断が割れる指摘／仕様・方針の変更を伴う指摘／自分が書いていないコードへの実害系の指摘／**マージ**（マージは常にユーザー判断）
- **例外: 自動マージのリポ**（6 の例外と同じリポ）だけは、エージェントの判断でマージしてよい。レビュー 1 巡の対応後の「再レビュー or マージ」をエージェントが決める。判断の目安と実行の場所はそのリポ側の文書（例: `.claude/ARCHITECTURE.md`）があればそれが正典。client / product リポ・破壊的変更・後戻りしづらいものは対象外で、引き続きユーザーへ投げる

## やってはいけないこと

- 再レビューの基準を満たさないまま、push / commit のたびに頼む（6 の例外を除く）
- 自動マージのリポの例外を、自動マージにしていないリポやエージェントが作ったものでない PR へ広げる
- 「念のため」を理由に、基準を満たさないまま頼む
- 数分待っても来ないからもう一度頼む（到着待ちは 4.3 に任せる）
- closed / merged の PR に頼む
- 振り分けの結果を「軽そうだから」と手で light に変える（変えたいなら classify.sh の基準を直す PR を出す）。heavy へ倒す（ユーザーの「重めで」）のはよい
- レート制限・上限で止まったツールを「レビュー済み」に数える
