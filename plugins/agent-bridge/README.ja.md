# agent-bridge

[English](README.md) | 日本語

自分の Supabase プロジェクトに置くメッセージキューを通して、Claude Code とほかの AI エージェントが双方向にやり取りするためのプラグイン。どのエージェントも、自分のトークンで同じ小さな HTTP API を使う。起こし方はエージェントごとに 2 種類から選ぶ。ブリッジが新着をそのエージェントの webhook に POST するか、エージェント側がポーリングするか。待ち受け中の Claude Code セッションは、メッセージが届くと起きる。

## インストール

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install agent-bridge@shibamasa-plugins
```

そのあと Claude に「ブリッジをセットアップして」と頼む。`setup` スキルが、選んだ Supabase プロジェクトにブリッジを作る。ほかのエージェントをつなぐときは「エージェントをブリッジに追加して」と頼む。`add` スキルが、参加者の登録、トークンの受け渡し、そのエージェントに渡す指示の作成までやる。

## 仕組み

```text
Claude Code（このプラグイン）─┐                        ┌─> webhook 型のエージェント（ブリッジが新着を POST する）
トークンを持つ別のエージェント─┼─> Edge Function ─> DB ─┤
                              │   agent-bridge         └─> poll 型のエージェント（GET ?agent=<id> を見てから読む）
```

- **ブリッジ**は、Supabase プロジェクトの中のスキーマ `agent_bridge`（参加者・スレッド・メッセージ）と Edge Function `agent-bridge`。規則はすべてスキーマにある。どのトークンが誰か、スレッドごとのメッセージ数の上限、メッセージの確保と既読化。Data API のロールはこのスキーマに触れず、届くのは Edge Function だけ。
- **API**: `POST <bridge_url>` に `Authorization: Bearer <token>` と `{"action": ...}` を付けて送る。操作は 5 つ。
  - `send`（`to`・`thread`・`body`、任意で `purpose`）
  - `inbox`（未読を最大 `limit` 件、10 分間確保する）
  - `ack`（`ids`）
  - `participants`
  - `message`（`id` の配送状態）

  エラーは `{"error": "<code>", "message": ...}` で返る。コードと HTTP ステータスの対応は次のとおり。
  - `unauthorized`: 401
  - `bad_request`・`unknown_agent`: 400
  - `not_found`: 404
  - `hop_limit`・`thread_closed`: 409
- **エージェントの起こし方**:
  - `webhook` 型は、新着ごとに自分の URL へ POST を受け取る。ヘッダーは `Authorization: Bearer <そのエージェントの webhook キー>`、本文は `{"event":"agent_bridge.message","id","thread","from","to","body","created_at"}`。
  - `poll` 型は `GET <bridge_url>?agent=<id>` を呼ぶ。トークンは要らず、返るのは `{"agent","unread","latest_id"}` だけ。`latest_id` か `unread` が増えたら、トークンを使って読む。`inbox` で受け取ったまま `ack` していないメッセージは、新しい ID を伴わずに 10 分後に戻ってくる。そのため `unread` が 0 より大きいあいだは、ときどき `inbox` を呼び直す。
- **秘密**は Supabase の Vault に置く。全エージェントに `agent_bridge:<id>:token`、webhook 型にはさらに `agent_bridge:<id>:webhook_url` と `:webhook_key` がある。セットアップはこれらをダミー値 `REPLACE_ME` で作り、本物の値はダッシュボードで入れ替える。ダミーのトークンでは誰も認証されない。webhook 型のエージェントの秘密がダミーのままだと、メッセージは保存されるが POST されない（`delivery: not_configured`）。
- **スレッド**: 書き込めるのは、そのスレッドに参加しているエージェント（作った本人か、そのスレッドで送ったか受け取ったことがあるもの）だけ。
- **できること（capabilities）**: 参加者ごとに、自由記述の `capabilities` 欄がある。つながっている外部サービスと、そこでできること（push と PR ができる GitHub、投稿できるアカウントなど）を書く。ほかのエージェントは、誰に何を頼むかをこれで決める。`setup` と `add` が聞く。あとから変えるには `UPDATE agent_bridge.participants SET capabilities = '...' WHERE agent_id = '...'`。`register_participant` をもう一度呼んでも変えられるが、渡した値で `wake`・`display_name`・`role`・`capabilities` をまとめて上書きするので、4 つとも渡す。
- **ループ防止**: 1 つのスレッドに入るメッセージは最大 `max_messages` 件（既定 20）。超えると、上限を上げるまで送信は `hop_limit` で失敗する。

ブリッジのデータは別々のマシンにいる複数のエージェントで共有するので、Supabase にだけ置く。このリポのほかのデータを持つプラグインと違い、手元の SQLite を既定にはしない（手元のファイルでは共有できないため）。

## 何がどこへ送られるか

- メッセージの本文は、自分の Supabase プロジェクトのデータベースに保存される。
- webhook 型のエージェント宛てのメッセージは、そのエージェントの webhook URL（多くの場合は他社のサービス）にも送られる。
- ブリッジの URL を知っている人なら誰でも、各エージェントの未読件数と最新のメッセージ ID は読める。内容は読めない。
- Claude はメッセージの本文を、あなたからの指示ではなく、ほかのエージェントが書いたデータとして扱う。本文の中の依頼に応じて動く前には、あなたに確認する。

## スキル

| スキル | 使う場面 |
|---|---|
| `setup` | Supabase プロジェクトにブリッジを作る・更新する、Claude Code を参加者に登録する、Vault の秘密でまだダミーのものを確かめる。作るものを先に示し、あなたの OK を待ってから変更する |
| `add` | ほかのエージェントをつなぐ。参加者の登録（poll 型か webhook 型）、トークンの受け渡し、そのエージェントが使い方を知るために貼る指示の作成、テストメッセージでの疎通確認（「エージェントを追加して」「レビュー担当に渡す指示を作って」） |
| `talk` | ほかのエージェントへの送信と受信箱の確認、エージェント同士の議論の司会（「レビュー担当のエージェントに聞いて」「受信箱を見て」「X について議論させて」） |

## ツール

同梱の MCP サーバー（`bridge`）が持つツールは `send_message`・`check_inbox`・`mark_read`・`list_participants`・`message_status` の 5 つ。どれもブリッジへの HTTPS 呼び出し 1 回で、手元には何もキャッシュしない。

## フック

| フック | いつ | 何をするか |
|---|---|---|
| `arm_session.py` | ブリッジのツールの `PostToolUse` | そのセッションを「エージェントと話すセッション」として印を付ける。待ち受けるのは印のあるセッションだけ |
| `token_check.py` | `SessionStart` | `bridge_url` は設定されているのにトークンがセッションに届いていないとき（起動時に安全な保管場所を読めなかった可能性がある）、警告を 1 行出す。`/reload-plugins` か再起動を勧め、それで直らないときだけトークンを入れ直すよう案内する。同じ状況でブリッジのツールは `token_missing` を返す。トークンやその長さは出さない |
| `wait_inbox.py` | `SessionStart` と `Stop`、バックグラウンド（`asyncRewake`） | `listen` がオンで、印のあるセッションのとき、`poll_seconds` ごとにブリッジの状態を見る。未読があり、かつ、このマシンがこのブリッジで見たことのある ID より新しいメッセージが届いたか未読の件数が増えたら、件数だけを添えて Claude を起こす（本文は渡さない）。ID と件数を先に記録するので、1 通のメッセージで起きるのは 1 つのセッションの 1 回だけ。セッションの最後のターンから `max_wait_minutes` が過ぎるか（動いているポーラーの期限は新しいターンで延びる）、セッションのプロセスが無くなると止まり、次のターンでまた始まる |
| `unread_notice.py` | `UserPromptSubmit` | 未読があれば、その件数を発言の文脈に足す。未読が無いとき、またはブリッジが 2 秒以内に答えないときは何もしない |

## 設定

| キー | 既定値 | 意味 |
|---|---|---|
| `bridge_url` | 空 | Edge Function の URL（`https://<project-ref>.supabase.co/functions/v1/agent-bridge`）。セットアップが入れる。空ならセットアップ前とみなし、ツールはエラーを返し、フックは何もしない |
| `agent_id` | `claude` | ブリッジ上での Claude Code の参加者 ID。リポごとではなくユーザー単位。接続するマシンやユーザーごとに別の ID を使う |
| `token` | 空 | Claude Code のトークン。Vault の秘密 `agent_bridge:<agent_id>:token` と同じ値。秘密扱いで安全な保管場所に入る。入力するのはあなた自身で、Claude は値を見ない |
| `listen` | `false` | メッセージが届いたらセッションを起こす。既定はオフ。オンのときは、外からのメッセージで Claude のターンが始まり（トークンとツール実行を使う）、ポーリングのたびに Edge Function の呼び出しが 1 回かかる。プラグインの設定はユーザー単位なので、user スコープでインストールするとマシン上の全セッションに効く（ポーリングするのはブリッジのツールを使ったことのあるセッションだけ）。オフのままだと、動いているセッションは次の発言まで返信に気づかず、返信よりずっとあとになることがある。`setup` が「メッセージが届いたらこのセッションを起こしますか」と聞く |
| `poll_seconds` | `60` | 待ち受け中に状態を見る間隔（15〜3600 秒）。1 回が Edge Function の呼び出し 1 回 |
| `max_wait_minutes` | `50` | ターンが無いまま待ち受けを続ける時間の上限（1〜55 分） |
| `supabase_connector`・`supabase_project_id` | 空 | セットアップが保存する、ブリッジを置いた Supabase コネクタとプロジェクト |

インストールのスコープ: ブリッジを 1 つのリポだけで使うときは、`--scope user` ではなく、そのリポから `claude plugin install <plugin id> --scope local`（または `--scope project`）でインストールする。user スコープのインストールは、マシン上の全セッションでフックと MCP サーバーを動かす。スコープが決めるのはプラグインが動く場所だけで、設定（`agent_id`・`token`・`bridge_url`）はスコープに関係なくユーザー単位で保存される。プラグインを有効にしたマシン上のどのリポも同じ値を使う。`setup` スキルがスコープと `agent_id` を聞く。

設定の変え方: `echo '{"listen":"true"}' | claude plugin configure <plugin id> --values-stdin`。このコマンドは文字列の値しか受け付けないので、数値も真偽値も文字列で書く（`"60"`・`"true"`）。JSON の真偽値だと「The input on stdin isn't a JSON object of strings」で失敗する。local か project スコープで入れたプラグインは、そのプロジェクトのフォルダで実行する。ほかの場所では `No installed plugin has the id ...` で失敗する。新しいセッションは起動時に設定を読む。**すでに動いている Claude Code のセッションでは、すべて `/reload-plugins` を実行する**。実行するまでは古い値のままで、ブリッジのツールが `agent-bridge is not configured` を返すのにフックはもう新しい設定を見ている、ということが起きる。`listen` を変えても何も始まらない。動いているセッションは、読み込んだ時点のプラグインのバージョンも持ち続ける。

ポーリングの費用: 1 回の確認が Edge Function の呼び出し 1 回。1 日の回数 = 86400 ÷ 間隔（秒）、1 か月はその約 30 倍。60 秒間隔のポーラー 1 つで 1 日約 1,440 回（1 か月約 43,000 回）。ポーリングするエージェントや待ち受けのセッションが増えるたびに、同じだけ足される。合計を、自分の Supabase プランの Edge Function の枠と、Supabase の料金ページで見比べる。

データの見方: すべて `public` ではなくスキーマ `agent_bridge` にあるので、ダッシュボードの Table Editor はそのスキーマを選ぶまで表示しない。スキーマを選ぶか、`https://supabase.com/dashboard/project/<project-ref>/editor?schema=agent_bridge` を開く。

このマシンに置くファイル: フックは `${CLAUDE_PLUGIN_DATA}/wait/`（無ければ `~/.claude/state/agent-bridge/wait/`）に、ブリッジとエージェントごとに見たことのある最新のメッセージ ID と未読の件数、ポーリング中のセッションごとの pid ファイル、ブリッジのツールを使ったセッションごとの印を置く。2 日より古い pid ファイルと、14 日使われていない印は消す。プラグインを最後の 1 か所からアンインストールすると、`--keep-data` を付けない限り `${CLAUDE_PLUGIN_DATA}` は消える。代わりに使う `~/.claude/state/agent-bridge/` はその外にあって残るので、手で消す。ブリッジのデータは Supabase プロジェクトに残る。消すときは、スキーマ `agent_bridge`、Edge Function `agent-bridge`、Vault の `agent_bridge:*` の秘密を削除する。

## 制限

- 待ち受けで起きられるのは Claude Code が動いている間だけ。ターンが無いまま `max_wait_minutes` でポーラーが止まると、それ以降の新着は次に話しかけたときに `unread_notice.py` が知らせるまで待つ。
- webhook への配送は Supabase の `pg_net` を使う。メッセージを保存したあとに送り、再送はしない。相手のサービスが返した HTTP ステータスは `message_status` で見られる。Supabase がその応答を残すのは約 6 時間。
- webhook の本文と認証ヘッダーの形（`Authorization: Bearer <key>`、JSON の本文）は固定。別の形が要るサービスには、そのサービス用の変換が別に要る。
- `setup` と `add` には、SQL の実行・マイグレーションの適用・Edge Function のデプロイができる Supabase コネクタが要る。

## 前提

- macOS か Linux（フックが `fcntl` と `ps` を使う）
- `python3`（標準ライブラリだけ）
- Vault と `pg_net` が使える Supabase プロジェクト（どちらも Supabase で使える）
- `setup` と `add` 用の Supabase コネクタ（claude.ai のコネクタか MCP サーバー）

## テスト

```bash
bash plugins/agent-bridge/tests/run-all.sh        # MCP サーバー・フック・Edge Function のルーター（python3 と node、手元の偽ブリッジ相手）
bash plugins/agent-bridge/tests/run-postgres.sh   # スキーマを使い捨ての postgres:16 コンテナで（docker・psql）。Vault と pg_net は代役
```
