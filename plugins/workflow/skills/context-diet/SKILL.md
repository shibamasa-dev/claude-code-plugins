---
name: context-diet
description: セッション開始時に毎回積まれるコンテキストを実測して減らすスキル。2層を扱う — (A) 常時ロードテキスト（CLAUDE.md・rules・メモリ索引）を measure.py で実測し閾値超過時だけ圧縮、(B) 注入層（MCP コネクタ・skills 一覧）を inventory.py で棚卸しし、プロジェクト .claude/settings.json の deniedMcpServers / skillOverrides で落とす。「コンテキスト減らして」「初期ロード重い」「CLAUDE.md 重い」「メモリ肥大してない？」「常時ロード計測」「このプロジェクトで使わない MCP/スキルを切りたい」「コネクタ整理」で発動。検知は機械・判断は LLM・対象確定は必ずユーザー承認。
last_reviewed: 2026-09-06
review_after: 2027-03-05
---

# context-diet — 初期ロードの実測と削減

セッションが始まる前に積まれているものは2種類ある。**どちらか片方だけ見ると誤診する。**

| | Phase A: 常時ロードテキスト | Phase B: 注入層 |
|---|---|---|
| 中身 | CLAUDE.md・rules・メモリ索引 | MCP ツール名一覧・skills 一覧・MCP server instructions |
| 太り方 | 書き足されて**徐々に**太る | 最初から**全部載っている**（プロジェクトと無関係なものも） |
| 起動条件 | **閾値駆動**（超過時のみ） | **プロジェクト単位で一度棚卸し** |
| 出力 | ファイルの圧縮・退避 | プロジェクト `.claude/settings.json` |

体感で手を付けない。「ファイルが多い＝重い」は誤診（recall 時しか読まれないものは常時コストゼロ）。逆に **Phase A が ok でも Phase B が肥大していることがある**。片方の verdict をもう片方の結論にしない。

---

# Phase A — 常時ロードテキスト

## A-1. 実測（機械・常に安全）

```bash
python3 scripts/standing/measure.py --project <プロジェクトroot>   # 省略時 cwd
```

- 対象: グローバル CLAUDE.md／`~/.claude/rules/*.md`（frontmatter `paths:` 無しのみ）／プロジェクト CLAUDE.md・AGENTS.md・`.claude/CLAUDE.md`＋1階層 `@import`／`.claude/rules/`／メモリ索引 MEMORY.md
- 出力: JSON（合計 KB・トークン概算・索引の行長分布・索引↔本体の整合・`[[リンク]]`切れ・上位ファイル）
- exit 0=ok／1=超過（既定閾値: 常時合計 130KB・索引平均行長 100字。`--max-standing-kb` / `--max-index-avg` で変更）
- ローカル read のみ・認証不要・sandbox 内で動く

**ok なら Phase A は1行報告で終了。** 閾値内の grooming は時間の無駄（判断基準は `references/criteria.md`）。**ただしここで会話を終えない —— Phase B へ進む。**

## A-2. Grooming（LLM 判断・超過時のみ）

`references/criteria.md` の基準 1〜9 に従う。要点:

- **テキスト層で効く手段は3つだけ**: 圧縮／非自動ロードパス（例 `~/.claude/reference/`）への退避＋ポインタ化／rules の `paths:` glob 化。**rules/ への分割は削減にならない**（auto-load のまま）
- **運用ルールの実体は保持**。経緯・実例の長文は「日付＋結論1行」へ。承認日などの権威出典は残す
- **hook 等の機械強制点に移った規約**は本文を1行ポインタに圧縮してよい
- **索引は1行1フック**。全行 80字超が常態化したら書き直し
- **削除は「完了した project state」と参照切れだけ**。重複クラスタは統合しない
- **昇格は慎重に**（スリム化を打ち消す）

## A-3. 検証（必須）

1. 編集前に `cp` でバックアップし、バイト一致を確認してから編集
2. 圧縮後: 見出し parity（`diff <(grep -E "^#{2,3} " before) <(grep -E "^#{2,3} " after)` で消えた見出しゼロ）
3. 索引: `measure.py` を再実行し、整合系 breach（missing_from_index / missing_bodies / broken_wiki_links）がゼロ
4. before/after の KB を報告に併記

---

# Phase B — 注入層

レバーの仕様・検証コマンド・検証の限界は **[references/harness-levers.md](references/harness-levers.md)** に全部ある。**Phase B に入る前に必ず読む。**

## B-0. 絶対規則

> **対象の確定は必ずユーザー承認を得てから。無確認で settings.json を書かない。**

何が要るかはプロジェクトの中身とユーザーの意図でしか決まらない。エージェントの推測は当たらない。

- 提案は**グループ単位**で出す: ①claude.ai コネクタ（`deniedMcpServers`）②personal skills（`skillOverrides`）
- **グループごとに yes/no を取る**。「まとめて OK ですか」で済ませない
- **プラグイン／アカウント側スキルは提案に含めない。** `skillOverrides` が効かないため（harness-levers.md）。落としたいならプラグインごと `enabledPlugins` を切る話になり、それは全プロジェクトに波及するので別議題として立てる
- **迷ったものは残す。** 誤って切ると気づけない —— skills は一覧から消えるだけ、コネクタは tool が無いだけに見える
- ユーザーが個別に外したいものを言ったら、それを最優先で反映する

## B-1. 棚卸し（機械・収集のみ）

```bash
python3 scripts/injected/inventory.py --project <プロジェクトroot>
python3 scripts/injected/inventory.py --no-connectors   # 高速・オフライン
```

- 出力: コネクタ一覧（名前・状態・既に denied か）／skills 一覧（名前・description バイト数・既に override 済みか）／現行 `.claude/settings.json` の設定／合計
- **要否の判定は一切しない。** 判定はこのあと LLM とユーザーでやる
- `claude mcp list` を叩くのでヘルスチェック分の待ちが出る（数秒〜数十秒）

**inventory.py に出ないもの**（`not_enumerable` にも明記される）:
- アカウント側スキル（`small-business:*` / `anthropic-skills:*` / `design:*` 等）— ディスク上に無い
- 組み込みスキル（`code-review` / `simplify` / `schedule` 等）

この2つは**エージェント自身の skills 一覧から拾う**こと。

## B-2. 分類してユーザーへ提示

プロジェクトの中身（README・CLAUDE.md・言語・依存）を読んでから、各候補を「使う／使わない／判断つかない」に分ける。提示は**バイト数を添えて**、グループごとに。

判断の目安:

- **コネクタ**: そのプロジェクトの運用ドキュメント（CLAUDE.md・AGENTS.md）が名指しで要求しているものは残す。「あると便利かも」は落とす側
- **skills**: プロジェクト自前の `.claude/skills/` は絶対に触らない。他プロジェクトで現役のものも、このプロジェクトで発火しないなら `user-invocable-only`（`/名前` で呼べば動く）
- **既定値は `user-invocable-only`。** `off` は「二度と使わない」と言い切れるものだけ

## B-3. 生成と適用

承認されたグループだけで `.claude/settings.json` を組み立てる。

- **既存のキー（`hooks` 等）を壊さない。** 既存 JSON を読んで `deniedMcpServers` / `skillOverrides` を足すだけ
- 書き込み前に `cp` でバックアップ、バイト一致を確認
- 権限モードが `auto` だと分類器に拒否されることがある。その場合は完成ファイルをスクラッチパッドに出し、`cp` コマンドをユーザーに渡す（回避を試みない。詳細は harness-levers.md）

## B-4. 検証（必須）

```bash
claude mcp list                                     # 落としたコネクタが消えていること
claude mcp get "<残したコネクタ名>"                   # 残す側が生きていること
claude -p --model haiku 'Output ONLY JSON: {"<落とした skill>":<listed?>, "<残した skill>":<listed?>}' < /dev/null
```

- **対照を必ず取る。** 「落とした側が false」だけでは、元から載っていなかった可能性を排除できない。**残す側が true であること**を同じ実行内で確認する
- **さらに往復で確かめる。** 上の yes/no はモデルが幻覚する。false になった項目は **override を外して true に戻ることまで**見る。片道の観測を「実証」と呼ばない
- **`skillOverrides` は personal skill にしか効かない**（プラグイン・アカウント側スキルには無効。harness-levers.md 参照）。無効なキーを設定に残さない —— 効いているように見えて何もしていない
- headless では検証できないものがある（`name-only`・アカウント側スキル）。それは**未検証と明示して報告する**
- 最終確認はユーザーに `/context` を叩いてもらう。スラッシュコマンドは非対話セッションから実行できない

## B-5. ユーザーにしか実行できない操作の案内

このスキルの手順には**エージェントが実行できないもの**が混ざる。黙って諦めたり「あとでやっておいてください」で流したりせず、**コピペできる形で案内し、実行待ちであることを報告の最後に明示する。**

| 操作 | 誰が | なぜエージェントには無理か |
|---|---|---|
| `/mcp disable <server>` | ユーザー | スラッシュコマンドは非対話セッションから実行できない。ビルトイン MCP を落とす唯一の手段 |
| `/context` | ユーザー | 同上。固定費の実測はこれでしか取れない |
| `/reload-skills` `/reload-plugins` | ユーザー | 同上。設定変更の即時反映に要る |
| `.claude/settings.json` への書き込み | 場合による | 権限モードが `auto` だと分類器に拒否される。拒否されたら完成ファイルを出して `cp` を渡す |
| コネクタの OAuth | ユーザー | 認証フローは対話が要る |

**案内の型**（この5点を必ず添える）:

1. **何をするコマンドか**を1行で
2. **コピペできるブロック**（複数あるなら全部並べる。1つずつ小出しにしない）
3. **スコープ** —— プロジェクト単位か、全体に波及するか
4. **取り消し方**
5. **実行後に何を確認するか**

例:

```
/mcp disable claude-in-chrome
/mcp disable computer-use
```
- ビルトイン MCP をこのプロジェクトでだけ無効化します（合計 17.1k tokens 減）
- **プロジェクトスコープ**。`~/.claude.json` の projects エントリに記録され、他プロジェクトには波及しません
- 戻すのは `/mcp enable <name>`
- 実行後 `/context` の MCP tools が減っていれば成功

## ⚠️ `.claude/settings.json` はブランチで揺れる

git 追跡下に置くと、**ブランチを切り替えた瞬間に diet が on/off する**（設定を入れたブランチにしか存在しないため）。適用直後にこれを踏むと「効かなくなった」と誤診する。

- 恒久化するなら**早めに main へマージする**（以後のブランチが継承する）
- ブランチをまたいで安定させたいだけなら `.claude/settings.local.json`（git 追跡外）に置く。ただし共有できず、稼働中セッションに書き戻される可能性がある
- **検証中に「急に効かなくなった」ら、まず `git branch --show-current` を疑う**

---

## 報告の型

```
Phase A: <合計KB> / <ok|超過>   （超過時のみ before→after）
Phase B: コネクタ <before>→<after>、skillOverrides <件数>
確認済み: <検証コマンドで確かめた事実>
未確認: <headless で測れなかったもの>
次: 再起動 → /context で確定
```

推定と実測を同じ文体で並べない。数えただけのものは「推定」と書く。

## 定期実行

**Phase A のみ**月次で回す（肥大は遅い）。スケジューラには「measure 実行 → ok なら1行で閉じる → 超過時のみ grooming」の薄タスクを登録する。**Phase B は定期実行しない** —— プロジェクトごとに一度やれば済み、やり直すのは新しいコネクタ／スキルが増えたときだけ。

## Evals

```bash
python3 evals/run_evals.py   # フィクスチャを自動生成して検証・手作業ゼロ
```
