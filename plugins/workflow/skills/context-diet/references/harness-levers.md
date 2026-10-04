# 注入層のレバー（実測で確定した仕様）

システムプロンプトに毎回積まれる「ツール名一覧」「skills 一覧」「MCP server instructions」を、**プロジェクト単位で**削るための設定キー。2026-08-29 に Claude Code 2.1.251 のバイナリを読み、実機で検証した結果。

> ⚠️ ここに書いてあるのは**この時点の実測**。バージョンが上がったら再確認すること。検証コマンドは各項に併記した。

## どの層に何が置けるか

| 層 | ホワイトリスト | ブラックリスト | 範囲 |
|---|---|---|---|
| ユーザー `~/.claude/settings.json` | — | **`deniedMcpServers`** | このマシンの全プロジェクト |
| プロジェクト `.claude/settings.json` | — | **`deniedMcpServers`** / **`skillOverrides`** | プロジェクト |
| `~/.claude.json` の projects エントリ | `enabledMcpServers`（**`computer-use` 専用**） | `disabledMcpServers`（それ以外の全部） | プロジェクト |
| `.claude/settings.local.json` | `enabledMcpjsonServers` `enableAllProjectMcpServers` | `disabledMcpjsonServers` | `.mcp.json` 由来のみ |
| `managed-settings.json`（企業ポリシー） | `allowedMcpServers` | `deniedMcpServers` `disableClaudeAiConnectors` | マシン全体 |

ホワイト／ブラックはユーザーが選べない。**サーバー名で分岐が決まる**:

```js
var e0 = "computer-use";
function xve(e){ return e === e0 }
function _i(e){                                              // isDisabled(serverName)
  let t = li();                                              // プロジェクトエントリ
  if (xve(e)) return !Nte(t.enabledMcpServers).includes(e);   // ホワイトリスト
  return Nte(t.disabledMcpServers).includes(e);               // ブラックリスト
}
```

```bash
BIN="$(readlink -f "$(command -v claude)")"   # 実体は versions/<ver>
strings -a "$BIN" | grep -c 'function _i(e){let t=li()'
strings -a "$BIN" | grep -o 'e0="computer-use"'
```

## `deniedMcpServers`（コネクタを個別に落とす）

説明文は "Enterprise denylist" だが、**プロジェクト settings.json でもユーザー settings.json でも効く**（実測）。

**ユーザー `~/.claude/settings.json` に置けば「このマシンの全プロジェクト」に効く**（2026-09-15・Claude Code 2.1.272 で実測）。claude.ai 側のコネクタは有効なままなので、**他のデバイス・Web では使えるがこの PC だけ落とす**、という切り分けができる。用途例: freee をこの PC ではローカル MCP（`npx freee-mcp`）で使い、claude.ai のリモートコネクタと二重にならないようにする。

```json
"deniedMcpServers": [
  { "serverName": "claude.ai Notion" }
]
```

- entry は文字列でなく**オブジェクト**。`serverName` のほか `serverCommand`（配列）/ `serverUrl` も判定に使われる
- 名前は `claude mcp list` の表示名と完全一致（claude.ai コネクタは `claude.ai <表示名>` 形式）
- 落とすと**設定から消える**。接続断ではない（`claude mcp get "<名前>"` が "No MCP server named" を返す）
- headless 実行時に `Warning: claude.ai MCP servers blocked by enterprise policy: <名前>, ...` が**1行**出る。文言は固定で、設定ミスではない。`claude mcp list` には出ない

⚠️ **CLI 所有のビルトインサーバーには効かない。** `claude-in-chrome` と `computer-use` を `deniedMcpServers` に入れても無視される（blocked 警告にも出ない）。バイナリ内の理由コードが並列に定義されている:

```js
Pf = "Builtin server is CLI-owned; ignored"                              // ← ビルトインはこちらが優先
Af = "Blocked by enterprise policy (allowedMcpServers/deniedMcpServers)"
```

ビルトインを落とすなら `/mcp disable <name>`（`~/.claude.json` の projects エントリに書かれる。`computer-use` だけは `enabledMcpServers` ホワイトリストからの除去になる）。**settings.json には書かない** —— 効かない設定を残すと、効いているつもりで放置される。

**検証**:
```bash
claude mcp list                     # 一覧から消えていること
claude mcp get "claude.ai Notion"   # "No MCP server named" が返ること
claude -p 'reply OK' </dev/null 2>&1 | grep blocked   # blocked 警告に名前が載ること
```

## `skillOverrides`（skills 一覧から落とす）

```json
"skillOverrides": {
  "gws-gmail": "user-invocable-only",
  "coderabbit:code-review": "off",
  "mysql": "name-only"
}
```

| 値 | 挙動 |
|---|---|
| `off` | モデルからも `/名前` からも消える |
| `user-invocable-only` | **モデルからは消えるが `/名前` で手動起動できる** ← 削減目的の既定 |
| `name-only` | 名前だけ残し description を落とす |
| 未指定 | そのまま |

- 削減量は description のバイト数がそのまま効く

⚠️ **効くのは personal skill（`~/.claude/skills/*`）だけ。プラグイン由来スキルには効かない。**
`frontend-design` / `mcp-apps:*` / `coderabbit:*` で、`plugin:skill` 形式（`"frontend-design:frontend-design"`）と bare 形式（`"frontend-design"`）の両方を、`settings.json` と `settings.local.json` の両方に置いて試したが、いずれも一覧から消えなかった。**プラグインスキルを落とす手段は skillOverrides には無い**（プラグイン自体を `enabledPlugins` で無効化するしかない）。アカウント側スキル（`small-business:*` 等）も同様に効かないとみてよい。

**検証**（headless セッションは設定を読み直すので、本セッションを再起動しなくても測れる）:
```bash
claude -p --model haiku 'Output ONLY JSON: {"<落とした skill>":<listed?>, "<残した skill>":<listed?>}' < /dev/null
```

⚠️ **この yes/no 質問はモデルが幻覚する。** 「落とした側が false・残した側が true」が揃っても、それだけでは信用しない。**往復で確かめる** —— override を外して同じ質問をし、false だった側が true に戻ることまで見る。これを怠って「プラグイン prefix も効く」と誤った結論を出したことがある。最終確認は `/context` の Skills 表（ユーザーに叩いてもらう）。

## プラグイン由来の MCP サーバー・スキルのスコープ

プラグインが持ち込む MCP サーバー（`plugin:<plugin>:<server>`）とスキルは、**`enabledPlugins` を書いたスコープ**で効く。スキーマの記述:

> Enabled plugins using plugin-id@marketplace-id format. **Settings precedence is user < project < local < flag < policy**, so to disable a plugin that project settings enable, set it to false in `.claude/settings.local.json` — setting false in `~/.claude/settings.json` is overridden by the project.

つまり `~/.claude/settings.json` の `enabledPlugins` に書いたプラグインは**全プロジェクトで有効**になる。特定のリポでしか要らないプラグインは:

- user 設定から外し、**そのリポの project settings** に `{"<plugin>@<marketplace>": true}` を書く。`extraKnownMarketplaces` も一緒に移す（スキーマに "Typically used in repository `.claude/settings.json` to ensure team members have required plugin sources" とある）
- ⚠️ **user 側に `false` を書いても効かない**（project が上書きする）。無効化は `.claude/settings.local.json`

**受け皿の選び方** —— そのプラグインが常駐セッションの生命線なら **`.claude/settings.local.json`（git 追跡外）を選ぶ**。追跡下の `settings.json` に置くと、そのリポがブランチを切り替えた瞬間に設定ごと消え、常駐セッションが静かに機能を失う。共有が要るなら `settings.json`、切替耐性が要るなら `settings.local.json`。

⚠️ **移す前に、そのプラグインを使うセッションの cwd を確認する。** launchd や外部トリガから起動されるセッションは cwd が想定と違うことがあり、project settings が読まれずプラグインごと落ちる。plist の `WorkingDirectory` と起動スクリプトの WORKDIR 既定の両方を見る。

**検証は3点セット**（移設後すぐ、常駐の再起動を待たずに測れる）:
```bash
cd <使わせたいリポ>   && claude mcp list | grep plugin:   # 出ること
cd <使わせたくないリポ> && claude mcp list | grep plugin:   # 出ないこと
cd <第3のリポ>        && claude mcp list | grep plugin:   # 波及していないこと
```

プラグイン MCP を1プロジェクトだけ落とすなら `deniedMcpServers` に `plugin:<plugin>:<server>` を書く方が影響が小さい（ビルトインと違いこちらは効く）。

## その他

- **`disableClaudeAiConnectors`**（bool）— スキーマ説明に "When true in **any settings source** … **a project can opt out**, but a project-level false cannot override a user-level true"。プロジェクト settings.json で使えるが**コネクタ全断**なので、GitHub 等を使うプロジェクトでは採れない
- **`~/.claude.json` の `disabledMcpServers`** — `/mcp disable <server>` が書き込み口（`/mcp enable` で戻る）。プロジェクト単位。`claude mcp remove` は削除であって無効化ではないので使わない
- **`disableBundledSkills`**（bool）— 同梱スキル・ワークフローを丸ごと落とす。粒度が粗すぎるので通常は使わない

## 検証の限界（ここは測れない）

- **`name-only` は headless では検証できない。** headless (`claude -p`) はそもそも skills 一覧に description を出さない（`- coderabbit:code-review` のみ）。確認するなら対話セッションを再起動して `/context` を見る
- **アカウント側スキル（`small-business:*` / `anthropic-skills:*` / `design:*` 等）は headless に載らない**ため、override が効いたか headless では測れない。ディスク上にも無いので `inventory.py` にも出ない。エージェント自身の skills 一覧から拾い、効果は再起動後の `/context` で確認する
- **`/context` はスラッシュコマンドなので非対話セッションからは実行できない。** ユーザーに叩いてもらって出力を貼ってもらうこと

## 書き込みについて

`.claude/settings.json` への書き込みは、権限モードが `auto` のとき**分類器に拒否されることがある**（`Permission for this action was denied by the Claude Code auto mode classifier`）。ハーネスの構造的なブロックではないので、拒否されたら:

1. ユーザーに権限モード（`~/.claude/settings.json` の `permissions.defaultMode`）を伝える
2. 完成ファイルをスクラッチパッドに出し、`cp` コマンドを渡す

回避を試みない。設定変更はユーザーが承認する対象。
