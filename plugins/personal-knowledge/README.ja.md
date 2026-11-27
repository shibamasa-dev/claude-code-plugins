# personal-knowledge

[English](README.md) | 日本語

個人のデータを手元のマシンに貯めるスキル群。`get-chrome-history` は Chrome の閲覧履歴を読んで興味の傾向をまとめ、実行するたびに使っているサイトを少しずつ覚えていく。`relationship-ledger` は知り合いや会った人の台帳を非公開で持つ。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install personal-knowledge@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `get-chrome-history` | 「ブラウザ履歴を分析して」「最近何を見てるか教えて」「閲覧傾向を教えて」。Claude が前回以降に増えた訪問を読み、サービスごと（動画・コード・ドキュメント・音楽・買い物・ニュース・SNS）にまとめ、まだ知らないドメインを分類し、傾向を JSON で返す。ユーザープロフィールやおすすめの材料に使える。実体は `skills/get-chrome-history/scripts/get_chrome_history.py`（Python・標準ライブラリだけ） |
| `relationship-ledger` | 「名刺を登録して」「この人どこで会った？」「知り合いを記録して」「要注意人物リスト見せて」。Claude が、人、いつどこで会ったか（`meeting` のメモ）、プラットフォームごとの SNS アカウント、出典付きのひととなりのメモ、フォローアップ、プロンプトインジェクションの試み、状態のラベル（`active`・`watch`・`avoid`・`blocked`・`archived`）を、同梱の MCP サーバー `ledger` を通してデータベースに記録し、名前・ハンドル・メモの文面で引く。写真は参照だけで、顔認識はしない |

## get-chrome-history の動き

1. **読む。** `chrome_profile` のプロファイルの History データベースを、`~/Library/Application Support/Google/Chrome/<profile>/`（macOS）、`~/.config/google-chrome/<profile>/`・`~/.config/chromium/<profile>/`（Linux）から探す。Chrome は起動中このファイルをロックするので、一時ディレクトリにコピーして読み、コピーは消す。Chrome のファイルには書かない。
2. **範囲。** そのプロファイルで前回見た一番新しい訪問より後の訪問を取る。プロファイルごとの初回は直近 7 日。
3. **振り分ける。** 訪問ごとに 3 つのどれかに入れる: `knowledge.json` にある既知のサービス（カテゴリ付き）、未知のドメイン（集計し、タイトルの例を付け、滞在時間の多い順に上位 20 件）、ノイズ（`min_visit_duration_seconds` より短い、`min_visit_count` より訪問が少ない、または `"ignore": true` を付けたサービス）。
4. **覚える。** Claude が未知のドメインを分類して自分の `knowledge.json` に足すので、次の実行から既知になる。
5. **まとめる。** Claude がカテゴリごとの傾向を利用者の言語でまとめる。根拠が薄い項目は空のままにする。

ページのタイトルは訪れたサイトが書いたものなので、スクリプトは制御文字を除いて 200 文字で切り、スキルはタイトルや URL の中の指示に従わないよう Claude に指示している。プラグインが保存するファイル（`knowledge.json`・`state.json`）は手元のマシンに残る。スクリプトが出力した履歴はそうではない。Claude との会話に入るので、範囲内の訪問の URL とタイトルは、セッションのほかの内容と同じくモデルの提供元へ送られる。あとで要約しても送られた事実は消えない。それでよいときだけスキルを使うこと。スキルは、生の URL やタイトルをよそに書くファイルやメッセージへ写さないよう Claude に指示している。

## relationship-ledger の動き

SQL は Claude が書く。プラグインが持つのはスキーマ（`migrations/sqlite/` と `migrations/postgres/`）と小さな MCP サーバー `server/ledger_mcp.py` で、`.mcp.json` に `ledger` として宣言し、`uv run --script` で起動する。サーバーがするのは SQL の実行（`execute_sql`）、マイグレーションの適用（`apply_migrations`。セッションの最初の呼び出しでも走る）、SQLite での `rl_norm()`（NFKC と小文字化）の提供だけ。どの書き込みでも守るべき決まりはスキーマが持つ: 許される状態・メモの種類・深刻度、確度 0〜5、キーの形式、`(platform, handle)` ごとに大文字小文字を区別せずアカウントは 1 つ、写真の参照には同意の根拠が必須、全テーブルの `updated_at`、変えられないキー。

- テーブル: `rl_people`（`taro-example` のような slug がキー）、`rl_social_accounts`、`rl_interaction_notes`、`rl_prompt_injection_events`、`rl_photo_refs`、`rl_schema_migrations`。ビュー: `rl_v_people`（1 人 1 行。プラットフォームごとの最新のアカウントと件数）と `rl_v_search`（検索できる文面すべて）。各列の説明はスキルの `references/schema.md`。
- データの置き場所は初回に 1 度だけ決めて `ledger_route` に保存する: `sqlite`（既定のファイル）、`postgres`（`ledger_database_url`）、`connector`（SQL を実行できる claude.ai のコネクタ。Supabase など）。保存した置き場所が使えないとき、Claude とサーバーは止まってそう伝える。台帳が 2 か所に割れるので、別の置き場所は開かない。
- 台帳に入れてよいものはスキルの `references/privacy-boundaries.md` にある: 知っている人・会った人だけ、出典があり直せるメモ、秘密は入れない、機微な属性を推測しない、位置の履歴は入れない、名刺の画像は既定では残さない、`avoid`・`blocked` は利用者が言ったときだけ。SNS のプロフィールや投稿は根拠として扱い、指示としては扱わない。Claude が台帳から読んだ内容は会話に入るのでモデルの提供元へ送られる。データベースそのものは置いた場所に残る。

## 設定

| キー | 既定 | 意味 |
|---|---|---|
| `chrome_profile` | `Default` | 読む Chrome のプロファイルのディレクトリ名（`Default`・`Profile 1` など）。空なら `Default`。そのプロファイルに History が無いときは、見つかったプロファイルを示す |

| `ledger_sqlite_path` | 空 | relationship-ledger の SQLite ファイル（`~` は展開する。相対パスはプラグインのデータディレクトリから）。空ならプラグインのデータディレクトリの `relationship-ledger/ledger.sqlite3`。`ledger_database_url` があるときは使わない |
| `ledger_database_url` | 空 | Postgres・Supabase の `postgresql://...`。`ledger` サーバーは SQLite の代わりにここへつなぐ。機密扱いで、`settings.json` ではなく安全な保存先に入る |
| `ledger_route` | 空 | 初回に Claude が保存する: `sqlite`・`postgres`・`connector`。保存した置き場所の設定が欠けているとき（`ledger_database_url` の無い `postgres`、ある `sqlite`）は、別の置き場所を開かずに毎回エラーにする |
| `ledger_connector_id` | 空 | `ledger_route=connector` のとき Claude が保存する: コネクタの `mcp__<server>__execute_sql` の `<server>` |
| `ledger_connector_project_id` | 空 | `ledger_route=connector` のとき Claude が保存する: コネクタの SQL ツールが要るプロジェクト ID（要るときだけ） |

プロファイルのディレクトリ名は、そのプロファイルで `chrome://version` を開くと、プロファイルのパスの行の末尾に出ている。

`ledger_` で始まるキーは `relationship-ledger` だけが使う。`/plugin` か `claude plugin configure personal-knowledge@shibamasa-plugins` で設定し、`/reload-plugins` を実行する。

### ファイルの置き場所

| ファイル | 場所 | 中身 |
|---|---|---|
| `knowledge.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | スキルが知っているサービスとフィルタ。初回に `skills/get-chrome-history/knowledge.json` の種をコピーし、以後は Claude が自分のコピーに足していく。プラグインを更新しても上書きしない |
| `state.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | 見た中で一番新しい訪問の時刻。History ファイルごとに持つので、`chrome_profile` を切り替えても取りこぼさない。消すと次は直近 7 日を取り直す |
| History のコピー | システムの一時ディレクトリ | 読み終えたらすぐ消す |
| `ledger.sqlite3` | `${CLAUDE_PLUGIN_DATA}/relationship-ledger/`、または `ledger_sqlite_path` | 既定の置き場所での relationship-ledger。`ledger_database_url` やコネクタのときは作らず、行はそのデータベースに入る |
| uv が落とす Python パッケージ | uv のキャッシュ（`uv cache dir`。たいてい `~/.cache/uv`） | SQLite の台帳は何も落とさない。`ledger_database_url` で初めて起動したとき psycopg を足す（PyPI から）。アンインストールしても残る。消すには `uv cache clean psycopg psycopg-binary` |

`${CLAUDE_PLUGIN_DATA}` は `~/.claude/plugins/data/personal-knowledge-<marketplace>/`。これが無い状態で動いたとき（ターミナルから手で動かしたときなど）は、代わりに `~/.claude/state/personal-knowledge/get-chrome-history/` を使い、そのことを標準エラーに出す。

**プラグインを最後に入っている場所からアンインストールすると、`--keep-data` を付けない限り `${CLAUDE_PLUGIN_DATA}` ごと `knowledge.json`・`state.json` と、その中の SQLite の relationship-ledger が消える。**

```bash
claude plugin uninstall personal-knowledge@shibamasa-plugins --keep-data
```

そのディレクトリの外にある `ledger_sqlite_path` の台帳、`ledger_database_url` やコネクタの先のデータベース、`~/.claude/state/` の代わりの置き場所は消えない。

## 制限

- 読めるのは macOS と Linux の Chrome・Chromium だけ。Windows、ほかの Chromium 系ブラウザ（Edge・Brave・Arc）、Firefox は読まない。
- 1 回に読むのは 1 プロファイル。
- サービスはホストとその親ドメインで照合する（`www.amazon.co.jp` は `amazon.co.jp` に当たる）。パスでは見ないので、同じホストにある 2 つのサービスは区別できない。
- relationship-ledger: 名刺の登録は複数の文に分かれ、それぞれ別にコミットされる（サーバーは 1 回の呼び出しで 1 文を実行する）。途中で失敗すると前の行は残るので、スキルはメモを足し直す前に確かめるよう Claude に指示している。ハンドルの重複判定は `lower()` を使い、SQLite では ASCII だけを畳む。upsert を使うので SQLite 3.24 以上が要る。JSON の `->>` 演算子は使わない。`ledger` サーバーは Claude が送った 1 文をそのまま実行する。SQLite では `ATTACH` を拒むので、台帳の外のファイルを開く文は通らない。Postgres では `ledger_database_url` のロールが届く範囲を決めるので、スーパーユーザーでないロールを使うこと。
- 範囲は URL ごとの最終訪問時刻で決まる。URL の `visit_count` と滞在時間は Chrome に残る累計で、範囲内の分だけではない。
- コピーは Chrome が書き込み中かもしれない時点で取る。コピーの時点で Chrome がまだ確定していなかった訪問は、それより新しい訪問がコピーに入っていると取りこぼす。

## 前提

- Google Chrome か Chromium
- macOS か Linux
- Python 3.9 以上（標準ライブラリだけ）
- relationship-ledger: [uv](https://docs.astral.sh/uv/)。`ledger` の MCP サーバーを起動する（`ledger_database_url` のときは初回に psycopg を落とす）。SQLite ならほかは要らない。`ledger_database_url` には Postgres 13 以上か Supabase。uv が無いと `ledger` サーバーは起動せず、スキルはそのエラーで止まる

## テスト

```bash
bash plugins/personal-knowledge/tests/run-all.sh        # オフライン。relationship-ledger の行は uv が要る
bash plugins/personal-knowledge/tests/run-postgres.sh   # relationship-ledger を使い捨ての postgres:16 コンテナで。docker・psql・uv が要る
```

オフラインで動く。どのケースも、Chrome の `urls` / `visits` テーブルと架空の URL で History データベースを一時ディレクトリに作り、`HOME`・`TMPDIR`・`CLAUDE_PLUGIN_DATA` をそこへ向けるので、本物のプロファイルやホームディレクトリは読み書きしない。確かめるのは、3 つの振り分け、初回の 7 日の範囲、差分の取得、プロファイルごとのカーソル、読めない History のコピー、初回の実行がデータディレクトリの `knowledge.json` と `state.json` だけを書く（スキルのディレクトリには何も書かない）こと、種のコピーが 1 回だけで上書きされないこと、代わりの置き場所、プロファイルが無いとき、Linux のプロファイルの場所、ASCII のロケールでの出力（プロファイルが無いときのエラーも）、出力を書けなかった実行が `state.json` を書かないこと、タイトルの整形。

relationship-ledger の行は、SKILL.md が教える検索・記録・名刺の登録・要注意リストの SQL を、MCP サーバーを stdio 越しに呼んで実行する。人物はすべて架空で、スクリプトごとに新しいデータディレクトリを使う。ほかに確かめるのは、まっさらな起動（新しい `HOME`・作業ディレクトリ・uv のキャッシュ）がデータディレクトリの `relationship-ledger/ledger.sqlite3` だけを書くこと、`ledger_sqlite_path` で移せること、マイグレーションが 1 度だけ適用され、もう一度走ってもスキーマと行が変わらないこと、どのテーブルでも UPDATE で `updated_at` が進み、手で書いた `updated_at`・`search_text` は置き換わること、制約が不正な行を拒むこと、使えない・食い違う置き場所はエラーになり SQLite に切り替わらないこと。`run-postgres.sh` は同じ行を Postgres で回し、psycopg が要る行（接続 URL のパスワードがエラーに出ないこと）と、コネクタの経路（マイグレーションのファイルだけを `psql` で 2 回流し、RLS が有効で、ビューが Supabase の API ロールから閉じていること）も確かめる。
