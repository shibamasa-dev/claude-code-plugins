---
name: issue-ops
description: GitHub issue を「作って」「issue にして」「issue 化して」「起票して」「タスク化して」「閉じて」「クローズして」「完了にして」「更新して」「親子に分けて」「親 issue / 子 issue / ゴール issue に分けたい」「大きい仕事を issue に割りたい」「Recurrence 付けて」「Arch Review にして」と言われたら、実行前に必ず読む手順。運用規約（Issue Fields の設定値、sub-issues の階層、body とコメントの書き分け、close 時の「## 結果」「## 次回への引き継ぎ」、Arch Review ゲート、日付・Priority の決め方、受け入れ基準の書式（Gherkin の使いどころ）、残件を issue にするか PR スタックの層にするかの判定）を含む。issue_write / gh issue create|edit|close を直接叩く前にこの skill を通す。
last_reviewed: 2026-10-06
review_after: 2027-03-21
---

# issue-ops — GitHub issue 運用手順

> issue 運用の規約の正典はここ。CLAUDE.md には「タスク発生時は issue を作り、手順はこの skill」の要点だけ置けばよい。

### 概要

タスクが発生したら **GitHub issue を作成し、Issue Fields がある組織ではそれでメタデータを設定**。プロジェクトボードへ auto-add で自動追加される設定なら Projects API は触らない。**操作は GitHub MCP が既定**（Issue Fields がある組織ではメタデータは組織レベルの Issue Fields を使う。ProjectV2 GraphQL は使わない）。**ただし MCP の `issue_write` が承認フォームを出す環境では、フォームを待たずに `gh` ＋ GraphQL で直接行う**（下の「MCP が承認フォームを出すとき」。issue の作成・更新・close にユーザー承認は要らない＝2026-10-02 確定）。

組織の値（GitHub 組織・issue の既定リポ・Issue Fields の表・プロジェクトボード）は、セッション文脈に「組織設定」という見出しの注入テキストがあればそれを使う。無ければプロジェクトの CLAUDE.md、それも無ければユーザーに聞く。推測で埋めない。対象リポジトリは github_repo など文脈から抽出し、不明なら組織設定の既定リポを使う。

### Issue Fields（Issue Fields がある組織のみ・組織レベル・全リポ共通）

以下はフィールド名と値の意味の運用ルール。フィールドの ID や組織ごとの差分は組織設定を見る（Issue Fields は組織所有リポでしか使えない）。

| フィールド | 型 | 値 |
|-----------|-----|-----|
| Priority | single_select | Urgent / High / Medium / Low |
| Start date / Target date | date | YYYY-MM-DD |
| Effort | single_select | High / Medium / Low（任意） |
| Recurrence | single_select | Weekly / Monthly / Quarterly / Semiannual / Yearly（未設定＝単発。繰り返しタスクには必ず設定） |
| Arch Review | single_select | Pending / Approved（未設定＝レビュー対象外） |
| Verification | single_select | Not needed / Pending / Verified（未設定＝Not needed 扱い）。実環境でしか確認できない受け入れ基準が残っているかを表す |

MCP では**フィールド名で指定**（single_select は `field_option_name`、date 等は `value`。定義確認は `list_issue_fields`）。状態・分類のメタデータはラベルでなく Issue Field を第一選択（1フィールド=1軸・オプション最小限・上限25個/組織）。**値の設定・読み取りは MCP 可。フィールド定義の作成・変更は `admin:org` が要るので GitHub UI で**。

### Issue 作成（MCP `issue_write` 1コール）

```
issue_write(method: "create", owner: "<org>", repo: "<repo>", title: "...", body: "...",
  issue_fields: [
    { field_name: "Priority",    field_option_name: "Medium" },
    { field_name: "Start date",  value: "2026-07-15" },
    { field_name: "Target date", value: "2026-07-31" }
  ])
```

- 更新は `method: "update"` + `issue_number`。読み取りは `issue_read` の `field_values`／一覧・絞り込みは `list_issues(field_filters: [...])`。

### MCP が承認フォームを出すとき（gh ＋ GraphQL で直接）

Claude デスクトップアプリの Code タブなど、`issue_write` が「interactive form has been shown」を返す環境では、ユーザーが Submit するまで何も起きない（2026-10-02 実測: フォームが 4 件溜まり、作ったつもりの issue が無かった。Submit してもらっても Issue Fields が入っていなかった例もある）。**フォームが 1 回出たら、そのセッションの issue 操作はすべて下の方法に切り替える**（読み取りの `issue_read` はフォームが出ないので MCP のままでよい）。

| 操作 | コマンド |
|---|---|
| 作成 | `gh issue create --repo <o>/<r> --title "…" --body-file <file>`（本文は先にファイルへ書く） |
| 本文・タイトル更新 | `gh issue edit <n> --repo <o>/<r> --body-file <file>` |
| コメント | `gh issue comment <n> --repo <o>/<r> --body-file <file>` |
| close | `gh issue close <n> --repo <o>/<r> --reason completed`（`## 結果` を body に書いてから） |
| 親子（sub-issue） | `gh api -X POST repos/<o>/<r>/issues/<親>/sub_issues -F sub_issue_id=<子の .id（数値。node_id ではない）>` |
| Issue Fields 設定 | GraphQL `setIssueFieldValue(input:{issueId:<issue の node_id>, issueFields:[{fieldId:<id>, singleSelectOptionId:<id>}, {fieldId:<id>, dateValue:"YYYY-MM-DD"}]})` |
| Issue Fields 読み取り | GraphQL `repository(…){issue(number:N){issueFieldValues(first:10){nodes{… on IssueFieldSingleSelectValue{name field{… on IssueFieldSingleSelect{name}}} … on IssueFieldDateValue{value field{… on IssueFieldDate{name}}}}}}}` |

- フィールドとオプションの ID は `organization(login:"<org>"){issueFields(first:20){nodes{__typename … on IssueFieldSingleSelect{id name options{id name}} … on IssueFieldDate{id name}}}}` で引く（ID を推測で書かない）。
- 設定したら上の読み取りで値が入ったことを確かめる。

### 受け入れ基準の書き方（Gherkin を使う / 使わない）（2026-09-22 確定）

受け入れ基準は **body に inline**（正解を定義するもの＝閉じるまで変わらない）。**振る舞いが変わる issue だけ Gherkin（Given/When/Then）、それ以外は箇条書き。**

30 秒判定: **Then に観測可能な実値（列名・フラグ・件数・ファイル名）を 2 行以上書けるか。** 書けないなら箇条書き。

| Gherkin にする | 箇条書きのまま |
|---|---|
| 入力と期待出力を実値で書ける振る舞い変更 | 文書・設定・依存更新・リファクタ（Then が「変わらないこと」しか書けない） |
| 分岐の網羅が主題（INSERT/UPDATE、正常/stale/競合/空/エンコーディング） | 正常系 1 本だけ。3 行の箇条書きで足りる |
| バグ報告の再現条件（Given に実データ・実状態） | `Arch Review: Pending`（振る舞いが未確定。先に書くと決めた気になる） |
| 委譲 seed の受け入れ基準（実装 agent が経緯ゼロで読む） | 時間軸・複数アクターの相互作用が主題 → `sequenceDiagram` の領域 |

書き方（過去の実例「取込処理の UPDATE 経路でフラグを立て忘れたのに全テスト緑」を構文で潰す形）:

```gherkin
Scenario Outline: 伝票ファイルの取込で印刷対象フラグが立つ
  Given 受注番号 <受注番号> が <既存状態>
  When  伝票ファイル <ファイル名> を取込処理に通す
  Then  印刷対象フラグが '1' になる
  And   <正典で定めた他の更新列> が更新される

  Examples:
    | 既存状態                     | 受注番号 | ファイル名 |
    | 未登録（INSERT 経路）         | <実値>   | <実ファイル名> |
    | 別経路で登録済み（UPDATE 経路） | <実値>   | <実ファイル名> |
```

（**Examples の列は全部ステップから参照する**。どのステップも使わない列＝飾りで、読み手が行の違いを判別できない。`<実値>` は実サンプルから引いて埋める — 埋められないなら合成せず実データを要求する）

- **Then は正典（仕様）の更新列一覧から起こす。実装の SET 列を見て書かない** — 実装のバグが受け入れ基準に写り、緑が正しさの証拠でなくなる
- **Examples は経路ごとに 1 行**（INSERT が通っても UPDATE は別に通す。分岐ごとに実ファイル起点の通しを持つ）
- **Given には実ファイル名・実値を書く** — 中間状態を合成しないと書けないなら、それは実データ未入手のサイン（「無いので skip」を検証済みとして書かない）
- **1 Scenario 3〜5 行。Given は 1 つ、And の連鎖は 3 つまで**（積み上げた 10 行は箇条書きより読みにくい）
- **Scenario 名とテスト名を 1 対 1 にする。** 実行系（Cucumber/behave 等）が無いなら Gherkin は人間向けの書式でしかないので、対応が付けられないなら箇条書きで十分（飾りの feature ファイルは二重仕様になる）
- 委譲 seed に入れるときは **「Scenario は受け入れ基準であってテストの実装形式ではない」を 1 行添える**（無いと、フレームワークが無いのに feature ファイルを作り始める）
- **PR 本文に Gherkin は貼らない。** 受け入れ基準 ✅/❌ の行から Scenario 名を引用するだけにする（二重管理を作らない）。PR で書き起こしたくなったら、issue に受け入れ基準が無いまま実装したサイン

### 残件を issue にするか PR スタックの層にするか（2026-09-21 確定）

**既定は層。issue は例外。** 「タスクが発生したら issue」を無条件に適用すると、同じ story の続きまで issue に積み上がる（実害: 1 PR で終わる残件が issue の山になり、後から読む agent がそれを未処理タスクとして扱う）。

30 秒判定: **main に戻ったら作れないもの＝層、main からでも作れるもの＝issue。**

| 観点 | スタックの層（`gh-stack` skill） | issue |
|---|---|---|
| 依存 | 今のブランチのコードに依存する（main 単独では作れない・レビューできない） | main から独立に作れる |
| 時期 | この作業（スタックがマージされる前）で自分がやる | 別セッション・後日に回す |
| story | 同じ issue の受け入れ基準を満たすための続き（backend→frontend→テスト→文書） | 別の目的・別リポ |
| 判断 | 仕様が決まっていて作るだけ | ユーザーの設計判断・Arch Review が要る |
| 性質 | 今の変更で必要になったもの | 既存コードのバグ・周辺改善（委譲の受け入れ基準「報告のみ」の対象） |

- 層にするなら `gh-stack` の設計指針どおり「別の関心事が今作ったものに依存する」単位で 1 層。層の名前は `<topic>/<concern>`。
- どちらにも当てはまらないものは PR 本文の `## スコープ外の気づき` に置く。**ただし置きっぱなしにしない**: マージ前に 1 件ずつ「層 / issue / やらない（理由）」を書く。「やらない」は PR 本文に理由付きで残せば十分で、issue は作らない。
- 委譲した subagent が残件を報告してきた場合も同じ表で振り分ける。「報告のみ」は subagent が勝手に直さないためのルールであって、報告された残件が自動的に issue になるルールではない。

### issue の階層と依存（2026-09-08 決定）

**3件以上のステップがある／2週間以上かかる仕事は「ゴール issue ＋ 子 issue」に分ける。** GitHub ネイティブの sub-issues を使う（body のリンクで擬似的にやらない。親に進捗バーが出て、agent が `issue_read` で親→子を辿れる）。

| 層 | 何を書くか |
|---|---|
| **ゴール issue（親）** | 完了条件・今どこまで来たか・子の一覧（自動）。**作業内容は書かない** |
| **子 issue** | ステップ／バグ／改善。1件＝1つの成果物（PR・レポート・調査メモ） |

- **深さは2段まで**。孫を作りたくなったらゴールの切り方が大きすぎるサイン
- 親子は `issue_write` の `parent_issue_number`（起票時）か `sub_issue_write`（後付け）
- **横の依存**（A が終わらないと B に着手できない）は GitHub の issue dependencies（*blocked by*）で表す。MCP に無いので GraphQL `addBlockedBy(input:{issueId, blockingIssueId})`／読み取りは `issue { blockedBy blocking }`（2026-09-08 に API の存在を実測）
- **やりすぎない**: 単発タスク（購入・提出・1回の調査）に親は要らない
- 週次の「今週やること」は **open なゴール issue の子 issue 一覧**から出す（進捗レポートの「来週の予定」をゴールの代わりにしない）
- 子を close するときも「issue close 時の記録ルール」どおり `## 結果` を body に。親の close は全子が閉じてから、親 body の「今どこまで来たか」を完了形に書き換えて

### アーキテクチャレビュー・ゲート（Arch Review）

何が構造変更か、GO までに許されること、PR 本文の `Arch-Review:` 欄は review プラグインの `dev-flow` スキルが正典。ここには issue 側の操作だけ置く（dev-flow が無い環境でも、下の3行は守る）。

- 構造変更を伴う issue は起票時に `Arch Review: Pending` を設定し、body に採用案・設計要件を書く。`Pending` の間は実装 PR を出さない。委譲するときは seed にゲートの状態を書く。
- 解除はユーザーが `Approved` に変更（または明示 GO）してから。未設定はレビュー対象外。
- 機械抽出: `list_issues(field_filters: [{field_name:"Arch Review", value:"Pending"}])`。

### 実機検証ゲート（Verification）（2026-09-23 確定）

**「コードは終わったが、実環境に触れないので確かめていない」を追えるようにする軸。** GitHub の状態（PR が merged か・issue が open か）からは導出できないので Issue Field に置く。導出できるものはフィールドにしない（二重管理になり陳腐化する）。

| 値 | いつ付けるか |
|---|---|
| `Pending` | 受け入れ基準のうち**実環境でしか確認できない項目**が未実施のまま close / マージする |
| `Verified` | 実機で確認できた（実配線 issue の完了時に、関連 issue の値もここへ更新する） |
| `Not needed`（未設定も同義） | 実機検証が要らない（文書・設定・リファクタ） |

- **`Pending` は close を妨げない。** `## 結果` に「やらなかったこと（意図的）」として未検証項目を書き、残件の行き先（実配線 issue 等）を示したうえで close してよい。フィールドは閉じた後も残るので追える。
- 機械抽出: `list_issues(field_filters: [{field_name:"Verification", value:"Pending"}])`（**close 済みも対象にするため state は all**）。「動いているつもりだが誰も確かめていないもの」の一覧になる。
- `Arch Review: Pending`（実装前のゲート）と値の名前が同じだが軸が別。**Arch Review は着手してよいかの事前ゲート、Verification は終わった後に実機で確かめたかの事後ゲート。**

### Priority 設定ルール

ユーザー指定あり→その値／緊急・即対応→Urgent／Start date が近い・過去→High／指定なし→Medium。

### Status（プロジェクトボードのレーン）

Todo / In Progress / Done は Project 組み込み Status フィールドで **MCP では操作不可**（レーンは手動運用）。自動化する場合のみ GraphQL `updateProjectV2ItemFieldValue`（projectId は組織設定）。同名の Issue Field を作っても代替にならない。

### 繰り返しタスクの起票・実行の使い分け

Recurrence は分類・絞り込み用で実行トリガーではない。**記録を残す価値がある実タスク**→スケジューラが周期毎に自動起票（Recurrence＋前回 issue リンク付き）／**単なるリマインド・定例**→issue を作らずリマインダー・定例ルーチン側で処理。

### issue 更新時の書き分け（body と コメント）

**書くタイミングは「決定した瞬間」。セッション終了時にまとめて書かない。** 読んだ issue を更新しないまま数ターン経つと、workflow プラグインの hook `issue-writeback` が Stop を block して書き戻しを促す（issue ごと最大 3 回）。決定が本当に無い（要約だけ・実装の仕様として読んだだけ）なら、hook の指示文にある `dismiss` コマンドを理由付きで実行して終了する。`/clear`・compact・resume 後は未反映 issue を再通知する。全セッション横断の追跡状況は `issue-writeback status --pending`（`claude agents --json` と突合してセッション名・生死を出す。終了済みで未反映が残るものには resume コマンドが付く）。

**body は「今どうなっているか」、コメントは「なぜそうなったか」**（2026-09-06 確定）。

| 置く場所 | 内容 |
|---|---|
| **body** | 現在の設計・仕様・残タスク・前提・完了条件・一次情報の根拠 |
| **コメント** | 変更の経緯・「なぜ書き直したか」・旧設計の説明・調査の途中経過 |

- **設計が変わったら body を書き換える**（訂正コメントを足して body を放置しない）。後続 agent は `issue_read` 1コールで **body しか読まない**ため、body が古いと誤った前提の上に作業が積まれる。
- **経緯を body に残さない**。旧設計の説明が body にあると、ざっと読んだ人が現行仕様と誤読する（2026-09-06 実例: ある issue の body に「旧設計は帳票だった」が残り、今も帳票を作る issue に見えていた）。
- **body に置くのは「閉じるまで変わらないもの」だけ。** 実測値・達成率・「今どこまで来たか」は再実行で変わるので、body には出し方（パス・再現コマンド）を書き、値は日付つきでコメントへ（2026-09-15 実例: ある issue の「110/141」が7日で 112/138 と食い違い、母数の定義まで変わっていた）。期待値・対応表・実サンプルは正解を定義するもので変わらないため body に inline する。
- 検証は機械で: 書き換え後に `旧設計` `なぜ書き直` 等のキーワードが body に残っていないか grep する。

### issue close 時の記録ルール（全 issue 対象）

close 後も別 issue・別 agent から参照される（agent は `issue_read` 1コールで body を読む。コメント散在は取りこぼす）。**結論はコメントでなく body に置く**:

| 対象 | close 前にやること |
|------|------------------|
| すべての issue（completed） | body 末尾に `## 結果`（1〜5行: 結論／やった・やらなかった／参照 PR） |
| Recurrence 設定済みの再発性タスク | 詳細版 **`## 次回への引き継ぎ`**: 実施日／提出方法・提出先／使った画面・ツール／添付書類の要否と根拠／リードタイム／つまずき／改善メモ |
| duplicate / not_planned | body 追記不要（`state_reason` と1行コメント） |

- 判定基準は「次にこの issue を開くのは誰で、何を知りたいか」。コメントは途中経過ログとして任意。
- 自動化エージェントが代行 close する場合、記録が薄ければ close 前にユーザーへ1問だけ確認（未記録のまま close しない）。
- 再発性タスクの次回 issue は前回リンクを張り、`## 次回への引き継ぎ` をコピーして叩き台に。

### PR と issue の連動（`Closes` / `Refs`）（2026-09-23 確定）

**PR 本文には必ず `Closes <owner/repo#N>` か `Refs <owner/repo#N>` のどちらかを書く。** どちらも無い PR はマージ後に issue と辿れなくなる。**クロージングキーワードは別リポでも効く**（実測 2026-09-23: 実装 PR と issue が別リポでも、マージ2秒後に自動 close された）。`Refs` は相互参照を張るだけで close しない。

| 書くもの | 条件 |
|---|---|
| **`Closes`** | その issue の**受け入れ基準が全項目 ✅** になる見込み。**マージ前に `## 結果` を issue の body に書き終える** |
| **`Refs`** | 上のどちらかが欠ける。**PR 本文に「未達の項目」と「残件の行き先（層 / issue 番号 / やらない）」を書く** |

- **`## 結果` は `Closes` の PR をマージする前提条件**。自動 close は body に記録を残さないので、マージの後に書くと記録の無い close になる（PR を作る時点で `Closes` を書くのはよい）。review プラグインの `dev-flow-gate` フックが入っていれば、書いていないマージを止める。
- **`Refs` にした issue を閉じるのは委譲元（main セッション）の責務。** 委譲先（subagent・別セッション）のスコープは「PR 作成まで」で、マージ後の始末は委譲先の担当ではない。ここが無主になると「PR マージ済み・issue open」が翌朝の planner まで残る（2026-09-23 に実例あり）。
- 機械で拾う: `search_pull_requests`（`is:merged <issue番号>`）と issue の state の突き合わせ。朝の定期チェックを置いているならそれが安全網になるが、**ルールは「翌朝気づく」を「PR を出す時点で決まっている」に前倒しするためのもの**。

### 日付フィールドの入力ルール

**期限が明確**（年末調整・確定申告・契約更新等）→一般的な期限から能動的にスケジュール提示（例: 「Start date: 11/1、Target date: 11/30 で設定いたしましょうか？」）。**期限が不明確**→ユーザーに確認。

### 補足

MCP でカバーできないのはプロジェクトボードの Status レーン移動のみ（必要時だけ GraphQL）。Priority / 日付は Issue Fields（MCP）で完結。
