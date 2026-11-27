# research

[English](README.md) | 日本語

X や Web を読むスキル群。

- `research-x` は、選んだ X アカウントについて xAI の X 検索に問い合わせ、はっきりしたアップデート告知だけを、指定した言語と口調で要約し、1 件 1 メッセージで Slack に流す。
- `read-x-article` は、貼られた URL の X のポスト・長文ポスト・X Article を fxtwitter API 経由で 1 件読み、要約する。Markdown で保存するのは頼まれたときだけ。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install research@shibamasa-plugins
```

research-x を使うなら、プラグインの設定で `accounts`（投稿するなら `slack_channel` も）を入れ、資格情報 2 つを環境変数に置く（「資格情報」を参照）。read-x-article で保存もしたいときだけ `save_dir` を入れる。

## スキル

| スキル | 使いどころ |
|---|---|
| `research-x` | 「research-x 回して」「X のリリース告知を拾って」。Claude はまず必ず dry-run を走らせ、流す予定の中身を見せる。Slack に投稿するのは頼まれたときだけ。実体は `skills/research-x/scripts/research_x.py`（Python・標準ライブラリだけ） |
| `read-x-article` | x.com か twitter.com の status URL を貼って「読んで」「要約して」。「保存して」と言えば `save_dir` に Markdown で書く。指示だけのスキルで、スクリプトは無い |

## research-x の動き

1. チャンネルの直近 7 日分の履歴を読む（`--since-hours` がそれより長いとき、または、それより前から探した実行をやり直すときは、その分まで遡る）。research-x 自身の bot 投稿から、次に探し始める時刻と、投稿済みの X の status ID（各投稿の末尾に引用した status URL から）を取り出す。各投稿の metadata（`event_type: research_x_post`）には、その実行の開始時刻、探した範囲の始まり、最後の投稿だけ `last: true` を載せる。投稿を最後まで終えた実行の次はその開始時刻から、途中で落ちた実行の次は同じ範囲を探し直す。ただし、落ちた実行の投稿が直近 7 日の履歴に入っている間だけ。7 日より後にやり直すと、落ちた実行が見えないので初回として動き、その実行が流せなかった投稿は流さない。そうした投稿が無ければ 24 時間前から拾う。
2. アカウントを 10 件ずつ xAI に問い合わせる。X 検索は必須、推論は low、JSON スキーマは strict。
3. 対象アカウントの投稿のうち起点以降のものだけを残す。日時はモデルが返す値ではなく status ID に埋まっている時刻で判定し、チャンネルにある ID は落とす。
4. 古い順に 1 件 1 メッセージで流す。中身は区切り線、要約（Slack の制御文字はエスケープするので、要約が `@here` を飛ばすことはない）、引用の形にした投稿 URL。

ファイルも DB も持たない。状態はチャンネルの履歴だけなので、別のマシンから回しても同じ状態を見る。

**失敗したら流さない。** xAI への問い合わせが 1 つでも失敗したら 1 件も投稿せず exit 1 で終わる。次の実行は同じ起点からやり直す。接続の途中切断・5xx・途中までの応答は 1 回だけやり直し、4xx はやり直さない。

`--dry-run` は投稿しない。token とチャンネルがあれば履歴は読む。

## read-x-article の動き

1. URL からハンドルと status ID を取り出し、`https://api.fxtwitter.com/<ハンドル>/status/<ID>` を WebFetch で開く。x.com の URL は 402 が返るので直接は開かない。
2. 通常ポストと長文ポストは `tweet.text` を読む。X Article は `tweet.article.content.blocks[]`（Draft.js のブロック）をつないで Markdown にする。`preview_text` は冒頭だけ。
3. fxtwitter で本文が取れなければ tool.lu の写しを探す。無ければ取れた分を報告して終わる。
4. タイトル・著者・日付と短い要約を、話しかけた言語で報告する。保存を頼まれていなければここで終わる。
5. 保存は、頼まれたとき、かつ `save_dir` があるときだけ。1 件 1 ファイル `<YYYYMMDD>_Article_<ハンドル>_<Short_Title>.md` に、元の URL・全文・画像 URL を全部書く。`save_dir` に `INDEX.md` があれば、そのファイルの今の書き方で 1 行足す。索引を新しく作ることも、既存のファイルを上書きすることもない。

## 設定

`userConfig` のキー。プラグインを有効にするとき、または後から `/plugin` で入れる。

| キー | 既定 | 意味 |
|---|---|---|
| `accounts` | （必須） | X のハンドルをカンマ区切りで。`@` は付けない |
| `slack_channel` | 空 | 投稿先で、履歴を読むチャンネルの ID。投稿するなら必須 |
| `summary_language` | 空 | 要約の言語。空なら Claude に話しかけた言語。Claude を通さずに回すと英語 |
| `tone` | 空 | 要約の口調（自由記述）。空なら中立で事実に沿った口調 |
| `topic_filter` | 空 | 残す投稿の条件（自由記述）。空なら「アプリの機能追加・変更の告知だけ。研究結果は不要。はっきりしたアップデート告知だけ」 |
| `timezone` | 空 | プロンプトと結果に出す時刻の IANA タイムゾーン。空ならシステムのローカル |
| `model` | 空 | xAI のモデル。空なら実行のたびに xAI のモデル一覧から最新の素の `grok-<版>` を選ぶ |
| `save_dir` | 空 | 頼まれたときに read-x-article が保存するフォルダ。空なら保存しない |

`accounts` から `model` までは research-x の設定。スキルはこれらを環境変数（`RESEARCH_X_ACCOUNTS`・`RESEARCH_X_SLACK_CHANNEL`・`RESEARCH_X_LANGUAGE`・`RESEARCH_X_TONE`・`RESEARCH_X_TOPIC`・`RESEARCH_X_TIMEZONE`・`RESEARCH_X_MODEL`）でスクリプトに渡す。Claude を通さずに回すときは同じ変数を入れる。

### 資格情報

スクリプトは資格情報 2 つを環境変数から読む。`userConfig` には入れない。`sensitive` のオプションは MCP サーバーとフックには届くが、Claude が Bash で叩くコマンドには届かず、スキルはスクリプトを Bash で叩くため。

| 変数 | 中身 |
|---|---|
| `XAI_API_KEY` | xAI の API キー。`--dry-run` でも必須 |
| `SLACK_BOT_TOKEN` | Slack の bot token。scope は `chat:write` と `channels:history`（非公開チャンネルなら `groups:history`）。bot がチャンネルに参加していること。投稿には必須、`--dry-run` では任意（無ければ履歴を読まない） |

シェルのプロファイルに書くか、そこでパスワードマネージャーから読み込み、Claude Code に引き継がせる。どちらかが無ければ、スクリプトは変数名を示して exit 1 で終わる。

### 定期実行

プラグインは定期実行を持たない。毎日回すなら、自分のスケジューラ（cron・launchd・systemd timer・CI）から上の変数を入れてスクリプトを叩く。定期実行と手動実行を数分以内に重ねない。両方が同じ履歴を読み、同じ告知を流しうる。

### ファイルの置き場

research-x はファイルを書かず、DB も持たない。チャンネルの履歴が状態になる。

read-x-article が書くのは保存を頼まれたときだけで、書く先は `save_dir` だけ。1 件 1 つの Markdown ファイルと、そのフォルダに `INDEX.md` があればその 1 行。これは利用者自身の文書なので、プラグインをアンインストールしても残る。

アンインストールで消えるものは無い。

## 制約

- 同時に 2 つ走ると、同じ告知が 2 回流れうる（ロックは無く、状態はチャンネルの履歴だけ）。
- 投稿者が URL に無い投稿（`x.com/i/status/<id>`）は落とす。対象アカウントの投稿か確かめられないため。
- 要約はモデルが書く。research-x が確かめるのはアカウントと日時で、中身ではない。
- スキルは設定値をシングルクォートで囲んでコマンドに入れる。`'` を含む設定（`tone` か `topic_filter` くらい）は `'\''` とエスケープする必要がある。スキルは Claude にそうさせるが、値をそのまま写すとコマンドが壊れる。
- read-x-article はポストの URL を第三者のサービスである fxtwitter（`api.fxtwitter.com`）に送り、だめなら tool.lu で探す。どちらも止まっていたり、そのポストを持っていなかったりする。tool.lu には X Article の写しが無いことが多い。
- read-x-article は WebFetch で読む。WebFetch はページをモデルに渡すので、とても長い X Article は短くなって返ることがある。保存した写しに頼る前に、本文の終わりまで入っているか確かめる。
- 本物のサービスではまだ確かめていない。確かめたのは記録した応答と合成した応答だけ。未確認なのは、本物のチャンネルへの投稿、metadata の往復（`chat.postMessage` で書いた `run_started_at`・`since`・`last` を、`include_all_metadata` 付きの `conversations.history` で読み戻せるか）、英語のプロンプトを今の xAI のモデルに投げたときの結果。

### 初回の確かめ方

1. `XAI_API_KEY` だけで `--dry-run`。要約が指定した言語と口調で、指定したアカウントの分だけ返る。
2. `SLACK_BOT_TOKEN` と `slack_channel` を足して、もう一度 `--dry-run`。`history_read: true` になる。`not_in_channel` が出たら bot がチャンネルに入っていない。
3. 1 回投稿し、その実行の JSON 出力の `run_started_at` を控える。続けて `--dry-run` すると、`since` がその `run_started_at` と完全に一致するはず。`since` が最後の投稿の時刻の約 15 分前になっていたら、metadata が往復しておらず、research-x は投稿の時刻から推定している。その状態だと、途中で落ちた実行のあとの再実行が、その実行を終わったものとみなし、流せなかった投稿を拾わない。`since` が一致するまで定期実行には載せない（`since_source: slack_history` と `dropped.already_posted` はどちらの場合も同じになる。投稿済みの ID はメッセージ本文から取るため）。

## 前提

- research-x: Python 3.9 以上（標準ライブラリだけ）、xAI の API キー。投稿するなら Slack の bot token
- read-x-article: Claude Code の WebFetch と WebSearch。キーは要らない

## テスト

```bash
bash plugins/research/tests/run-all.sh
```

オフラインで回る。xAI と Slack は `tests/fixtures/` の記録した応答で置き換える。対象は research-x。read-x-article は指示だけのスキルで、テストするスクリプトが無い。
