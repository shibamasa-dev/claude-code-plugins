# creative

[English](README.md) | 日本語

画像・動画を作るときのスキル。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install creative@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `image-generation-prompt` | ページ・スライド・文書の質が上がるときに画像アセットを提案し、承認を得てから生成する。指示文は設定した経路（Codex・Gemini API・OpenAI Image API・fal.ai）向けに構造化する。計画の前に画像の履歴を検索し、試行はすべて記録する。参照画像は縮小したプロキシで残す |
| `motion-video` | 商品の画像・スクショ・ロゴ・実写クリップを載せたモーショングラフィックス動画を、コードで描いて書き出す |

`DESIGN.md` の lint は `lint` プラグインに移った。使い続けるなら `/plugin install lint@shibamasa-plugins` を実行する。

## MCP サーバー

`server/history_mcp.py`。`.mcp.json` で `history` として宣言し、`uv run --script` で起動する。画像の履歴に SQL を流すだけ:

| ツール | すること |
|---|---|
| `execute_sql` | Claude が書いた SQL を 1 文実行し、行を JSON で返す（最大 500 行） |
| `apply_migrations` | 未適用のマイグレーションを当て（最初のツール呼び出しでも走る）、バックエンド・SQLite ファイル・スキーマの版を返す |

SQLite では接続ごとに `img_norm(text)`（NFKC のあと小文字化）を登録する。Postgres では同じ関数をマイグレーションが作る。データベースは起動時ではなく最初のツール呼び出しで開く。保存先を勝手に切り替えない: `database_url` に繋がらなければ、どの呼び出しもそのエラーで失敗する。

## スキーマ

`migrations/sqlite/` と `migrations/postgres/` に同じスキーマを方言ごとに置き、名前順に当てて `img_schema_migrations` に記録する。どのファイルも 2 回当てて安全。

| オブジェクト | 中身 |
|---|---|
| `img_attempts` | 画像の試行 1 回につき 1 行（計画・生成した画像・却下した下書き・バリエーション）。`based_on` は作り直しが元にした試行、`route` は生成した経路、`status` は `planned`・`generated`・`accepted`・`rejected`・`failed`・`superseded` |
| `img_references` | 試行に付けた参照画像。`role`（`composition_only`・`style_only`・`palette_only`・`typography_only`・`subject_only`・`full_reference`・`none`）、元画像のハッシュとサイズ、プロキシのファイル名を持つ |
| `img_v_attempts` | 検索の入口。試行と、その参照画像の role の一覧 |

書き込みのたびに守るべき規則はスキーマに置いた: `CHECK` 制約、外部キー、挿入と更新のたびに `search_text` と `updated_at` を入れ（文が自分で書いた値は置き換える）・`id` の変更を拒むトリガー。時刻はどちらのデータベースでもミリ秒付きの UTC テキスト。Postgres では行レベルセキュリティをポリシー無しで有効にし、Supabase の API ロール `anon`・`authenticated` があればビューの権限を外す。

## 設定

| キー | 既定値 | 意味 |
|---|---|---|
| `image_routes` | 空 | 画像で試す経路の ID をカンマ区切りで先頭から順に: `codex`・`gemini`・`openai`・`fal`（例: `codex,gemini`）。空なら Claude が聞き、答えを保存するか尋ねる |
| `video_routes` | 空 | 動画で試す経路の ID を同じ形で: `gemini`・`fal` |
| `sqlite_path` | 空（データディレクトリの `image-history/history.sqlite3`） | 画像の履歴の SQLite ファイルの場所。`~` は展開し、相対パスはデータディレクトリからの相対 |
| `database_url` | 空 | Postgres・Supabase の `postgresql://...`。設定すると履歴のサーバーは SQLite でなくここに繋ぐ（`route` が `sqlite` で保存済みなら、両者が揃うまで止まる）。`sensitive` なので `settings.json` でなく安全な保管場所に入る |
| `route` | 空 | 画像の履歴の置き場: `sqlite`・`postgres`（どちらも同梱のサーバー経由）か `connector`。最初に使うときに Claude が決めて保存する。`image_routes` とは別物 |
| `connector_id` | 空 | `connector` のとき、コネクタのツール名のサーバー部分。Claude が保存する |
| `connector_project_id` | 空 | `connector` のとき、SQL ツールが要る `project_id`（Supabase）。Claude が保存する |

`/plugin` で設定するか、`echo '{"image_routes":"codex,gemini"}' | claude plugin configure creative@shibamasa-plugins --values-stdin` を実行してから `/reload-plugins` を実行する。経路ごとの呼び方は `skills/image-generation-prompt/references/routes.md` にある。`database_url` は自分で設定する。`route` とコネクタのキーは Claude が保存する。

### 画像の履歴への経路

- **`sqlite`**: 同梱の MCP サーバーで、SQLite のファイルに繋ぐ
- **`postgres`**: 同梱の MCP サーバーで、`database_url` に繋ぐ。あとで `database_url` が空になっても SQLite は開かずに止まる。`route` が `sqlite` なのに `database_url` が入っているときも、両者が揃うまで止まる
- **`connector`**: 自分の Postgres に SQL を流せる claude.ai のコネクタ（Supabase のコネクタなど）。スキーマの変更は `migrations/postgres/` のファイルをコネクタのマイグレーション用ツールで当てる。Claude はコネクタを名前ではなく、できることで探す

保存した経路が使えなくなったら、Claude は止まって知らせる。別の保存先に逃げないので、履歴が 2 か所に分かれない。参照画像のプロキシはどちらの経路でもこのマシンに残る。

### ファイルの置き場

| 何か | 置き場 |
|---|---|
| motion-video のプロジェクト（`brief.md`・`music-brief.md`・`verify.md`・`video.js`・`out/`） | 指定したフォルダ、無ければ作業ディレクトリの `motion-video/<slug>/` |
| motion-video の作業用の PNG 連番と音声 | `os.tmpdir()/motion-video/`。自動では消えないので、動画ができたら消す |
| 生成した画像 | 成果物のフォルダ（例: `assets/`）。経路には絶対パスで保存先を渡す |
| 画像の履歴のデータベース | プラグインのデータディレクトリの `image-history/history.sqlite3`。`sqlite_path`・`database_url` で移せる |
| 参照画像のプロキシ（JPEG、長辺 1280 px 以下） | プラグインのデータディレクトリの `image-history/references/` |
| BGM 用のサウンドフォント | `~/.local/share/motion-video/soundfonts/`（自分で置く） |
| uv が落とす Python パッケージ | uv 自身のキャッシュ（`uv cache dir`、ふつうは `~/.cache/uv`）。SQLite の履歴は何も落とさない。`database_url` を使う最初の起動で psycopg（約 24 MB、PyPI から）、最初のプロキシ作成で Pillow（約 28 MB）が入る。プラグインをアンインストールしても残る。消すなら `uv cache clean psycopg psycopg-binary pillow` |

## データについて

既定の画像の履歴と参照画像のプロキシは、プラグインのデータディレクトリ（`~/.claude/plugins/data/<plugin id>/`）にある。**プラグインを最後のスコープからアンインストールすると、このディレクトリが中の履歴とプロキシごと消える。** 残すなら `--keep-data` を付ける:

```text
claude plugin uninstall creative@shibamasa-plugins --keep-data
```

データディレクトリの外に置いた `sqlite_path` のファイルと、`database_url` やコネクタの先のデータベースは触らない。上の motion-video のファイルと生成した画像もデータディレクトリの外なので、アンインストールしても消えない。

## 前提

- `image-generation-prompt` は使う経路: サインイン済みの Codex CLI（`codex`）か、環境変数の API キー（`GEMINI_API_KEY`・`OPENAI_API_KEY`・`FAL_KEY`）
- 画像の履歴は [uv](https://docs.astral.sh/uv/)（MCP サーバーを起動し、最初に使うときにプロキシ用の Pillow と、`database_url` があれば psycopg を落とす）。SQLite ならほかに何も要らない。`database_url` には Postgres 13 以降か Supabase。uv が無いと `history` サーバーが起動せず、プロキシのコマンドも失敗する。image-generation-prompt は履歴なしでそのまま使える
- `motion-video` は Node.js・Chrome・ffmpeg

## テスト

```bash
bash plugins/creative/tests/run-all.sh        # SQLite。プロキシのテストに uv が要る
bash plugins/creative/tests/run-postgres.sh   # 同じテストを使い捨ての postgres:16 コンテナで。docker・psql・uv が要る
```
