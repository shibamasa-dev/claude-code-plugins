# inventory

[English](README.md) | 日本語

手持ちの物（電子部品・開発ボード・工具・消耗品・ガジェット）の在庫DB。Claude が現物の写真から登録し、読めなかった項目は `needs_review` に残し、NFKC 正規化した検索でいつでも引ける。保存先は既定で SQLite。Postgres / Supabase にも、直結か claude.ai のコネクタ経由で置ける。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install inventory@shibamasa-plugins
```

設定なしでも、プラグインのデータディレクトリの SQLite ファイルですぐ使える。

## スキル

| スキル | 使いどころ |
|---|---|
| `inventory` | 「10kΩの抵抗持ってたっけ？」「はんだごてどこ？」や、登録したい部品の写真。Claude は `norm()` を通して検索し、読めた列だけを書く upsert で登録する。読めなかった列は推測で埋めずに `needs_review` に残し、ラベルのパック数（`attrs.pack_qty`）と手元の数（`qty`）を分け、数えていない数量は断定しない |

## MCP サーバー

`server/inventory_mcp.py`。`.mcp.json` に `db` として宣言し、`uv run --script` で起動する。やることは次の 3 つだけ。

| ツール | 何をするか |
|---|---|
| `execute_sql` | Claude が書いた SQL を 1 文実行し、行を JSON で返す（最大 500 行） |
| `apply_migrations` | 未適用のマイグレーションを適用し（起動時にも走る）、バックエンド・SQLite のファイル・スキーマの版を返す |

SQLite では接続のたびに `norm(text)`（NFKC のあと小文字化）を登録する。Postgres ではマイグレーションが同じ関数を作る。サーバーが保存先を切り替えることはない。`database_url` に繋がらなければ、どの呼び出しもそのエラーで失敗する。

## スキーマ

`migrations/sqlite/` と `migrations/postgres/` に同じスキーマを方言ごとに持ち、名前順に適用して `inv_schema_migrations` に記録する。どのファイルも 2 回流して問題ない。

| オブジェクト | 中身 |
|---|---|
| `inv_items` | 1品目1行。主キーは `item_key`（変えられない slug）。`qty` は数えていなければ NULL、無くなったら 0。`needs_review` は未確定の列名（`qty,attrs.remaining`）。`location` は置き場、`photo_ref` は写真の参照 |
| `inv_categories` | `code`・`name`・`kind`（`part`・`consumable`・`tool`・`device`）。27 件入っていて、`INSERT` で足せる |
| `inv_v_items`・`inv_v_needs_review` | 検索の入口と、現物を見ないと確定しない行 |

毎回守るルールはスキーマが持つ。`CHECK` 制約とカテゴリへの外部キー、`inv_items` のトリガー 3 本（`search_text` の更新、更新のたびの `updated_at`、`item_key` の変更拒否）。時刻はどちらの DB でもミリ秒付きの UTC 文字列（`2026-10-11T09:30:00.123Z`）。Postgres では行レベルセキュリティを有効にしてポリシーは作らず、Supabase の API ロール `anon`・`authenticated` があればビューの権限を外す。

## 設定

| キー | 既定 | 意味 |
|---|---|---|
| `sqlite_path` | 空（データディレクトリの `inventory.sqlite3`） | SQLite ファイルの場所。`~` は展開し、相対パスはデータディレクトリから |
| `database_url` | 空 | Postgres / Supabase の `postgresql://...`。設定するとサーバーは SQLite ではなくここに繋ぐ。`sensitive` なので `settings.json` ではなく安全な保管場所に入る |
| `photo_dir` | 空（データディレクトリの `photos/`） | このマシンで Claude が写真を置く場所。`photo_ref` はここからの相対パス |
| `route` | 空 | `direct`（同梱サーバー）か `connector`。初回に Claude が判定して保存する |
| `connector_id` | 空 | `connector` のとき、コネクタのツール名のサーバー部分。Claude が保存する |
| `connector_project_id` | 空 | `connector` のとき、SQL ツールに渡す `project_id`（Supabase）。Claude が保存する |

経路は Claude が `claude plugin configure inventory@shibamasa-plugins --values-stdin` で保存する。`database_url` は自分で `/plugin`（または同じコマンド）から入れ、`/reload-plugins` する。

### 経路

- **直結**: 同梱の MCP サーバーで、SQLite か `database_url` に繋ぐ
- **コネクタ**: 自分の Postgres に SQL を流せる claude.ai のコネクタ（Supabase コネクタなど。`execute_sql(project_id, query)` は SQL 文字列しか受け取らないので、Claude は値をリテラルで埋め込む）。スキーマの変更は `migrations/postgres/` のファイルをコネクタのマイグレーション用ツール（`apply_migration`）で流す。コネクタは名前ではなく、できること（SQL を流せるか）で探す

保存した経路が使えなくなったら、Claude は止めて知らせる。別の保存先へは切り替えない（データが 2 か所に割れるため）。

## データの扱い

既定の SQLite ファイルはプラグインのデータディレクトリ（`~/.claude/plugins/data/<プラグイン ID>/`）の中にある。**最後の scope からアンインストールすると、このディレクトリごと、中の DB と写真が消える。** 残すなら `--keep-data` を付ける:

```text
claude plugin uninstall inventory@shibamasa-plugins --keep-data
```

そのディレクトリの外に置いた `sqlite_path` のファイルや `photo_dir`、`database_url` やコネクタの先の DB には触らない。

## 拡張

ベクトル検索のような任意の機能のために、プラグインのスキーマに列は作らない。使う人が自分の列か表（例: `my_item_embeddings (item_key, embedded_updated_at, embedding)`）と、それを更新するフック（例: `mcp__plugin_inventory_db__execute_sql` に合わせた `PostToolUse` フック）を足す。

更新する行は、行ごとに「前回その行を処理したときに記録した `updated_at`」と比べて見つける（`WHERE e.item_key IS NULL OR e.embedded_updated_at <> i.updated_at`）。表全体で 1 つの基準時刻（`updated_at > :last_run`）は使わない。同じ時刻の書き込みを取りこぼす。

## 制限

- SQLite のトリガーは同梱サーバーだけが持つ `norm()` を呼ぶ。ほかのクライアント（`sqlite3` シェル・DB Browser など）でもどの表も読めるが、`inv_items` への書き込みは `no such function: norm` で失敗する
- `attrs ->> 'key'` には SQLite 3.38 以上が要る
- Postgres のマイグレーションは `norm(text)` と `inv_` のオブジェクトを `search_path` の先頭のスキーマ（Supabase では `public`）に作り、同名の `norm(text)` が既にあれば置き換える
- `execute_sql` 1 回につき SQL は 1 文。バインドパラメータは無い（コネクタと同じ）

## 前提

- MCP サーバーの起動に [`uv`](https://docs.astral.sh/uv/)（初回に Python と `psycopg` を入れる）
- コネクタ経路では、SQL を流せてマイグレーションを適用できる claude.ai のコネクタ

## テスト

```bash
bash plugins/inventory/tests/run-all.sh        # SQLite。素の python3 で回す（CI が回すもの）
bash plugins/inventory/tests/run-postgres.sh   # 同じテストを Docker の postgres:16 で。マイグレーションファイルを psql だけで流す確認つき
```

どのテストも、Claude Code と同じように stdio でサーバーと話す（`tests/mcp_call.py`）。fixture は実際の在庫の行から、個人的な情報を除いたもの。
