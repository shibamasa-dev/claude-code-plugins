# research

[English](README.md) | 日本語

X や Web を読むスキル群。今は `research-x` の 1 つだけ。選んだ X アカウントについて xAI の X 検索に問い合わせ、はっきりしたアップデート告知だけを、指定した言語と口調で要約し、1 件 1 メッセージで Slack に流す。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install research@shibamasa-plugins
```

入れたら、プラグインの設定で `accounts`（投稿するなら `slack_channel` も）を入れ、資格情報 2 つを環境変数に置く（「資格情報」を参照）。

## スキル

| スキル | 使いどころ |
|---|---|
| `research-x` | 「research-x 回して」「X のリリース告知を拾って」。Claude はまず必ず dry-run を走らせ、流す予定の中身を見せる。Slack に投稿するのは頼まれたときだけ。実体は `skills/research-x/scripts/research_x.py`（Python・標準ライブラリだけ） |

## research-x の動き

1. チャンネルの直近 7 日分の履歴を読む（`--since-hours` がそれより長ければその分）。research-x 自身の bot 投稿から、次に探し始める時刻と、投稿済みの X の status ID（各投稿の末尾に引用した status URL から）を取り出す。各投稿の metadata（`event_type: research_x_post`）には、その実行の開始時刻、探した範囲の始まり、最後の投稿だけ `last: true` を載せる。投稿を最後まで終えた実行の次はその開始時刻から、途中で落ちた実行の次は同じ範囲を探し直す。そうした投稿が無ければ 24 時間前から拾う。
2. アカウントを 10 件ずつ xAI に問い合わせる。X 検索は必須、推論は low、JSON スキーマは strict。
3. 対象アカウントの投稿のうち起点以降のものだけを残す。日時はモデルが返す値ではなく status ID に埋まっている時刻で判定し、チャンネルにある ID は落とす。
4. 古い順に 1 件 1 メッセージで流す。中身は区切り線、要約（Slack の制御文字はエスケープするので、要約が `@here` を飛ばすことはない）、引用の形にした投稿 URL。

ファイルも DB も持たない。状態はチャンネルの履歴だけなので、別のマシンから回しても同じ状態を見る。

**失敗したら流さない。** xAI への問い合わせが 1 つでも失敗したら 1 件も投稿せず exit 1 で終わる。次の実行は同じ起点からやり直す。接続の途中切断・5xx・途中までの応答は 1 回だけやり直し、4xx はやり直さない。

`--dry-run` は投稿しない。token とチャンネルがあれば履歴は読む。

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

スキルはこれらを環境変数（`RESEARCH_X_ACCOUNTS`・`RESEARCH_X_SLACK_CHANNEL`・`RESEARCH_X_LANGUAGE`・`RESEARCH_X_TONE`・`RESEARCH_X_TOPIC`・`RESEARCH_X_TIMEZONE`・`RESEARCH_X_MODEL`）でスクリプトに渡す。Claude を通さずに回すときは同じ変数を入れる。

### 資格情報

スクリプトは資格情報 2 つを環境変数から読む。`userConfig` には入れない。`sensitive` のオプションは MCP サーバーとフックには届くが、Claude が Bash で叩くコマンドには届かず、スキルはスクリプトを Bash で叩くため。

| 変数 | 中身 |
|---|---|
| `XAI_API_KEY` | xAI の API キー。`--dry-run` でも必須 |
| `SLACK_BOT_TOKEN` | Slack の bot token。scope は `chat:write` と `channels:history`（非公開チャンネルなら `groups:history`）。bot がチャンネルに参加していること。投稿には必須、`--dry-run` では任意（無ければ履歴を読まない） |

シェルのプロファイルに書くか、そこでパスワードマネージャーから読み込み、Claude Code に引き継がせる。どちらかが無ければ、スクリプトは変数名を示して exit 1 で終わる。

### 定期実行

プラグインは定期実行を持たない。毎日回すなら、自分のスケジューラ（cron・launchd・systemd timer・CI）から上の変数を入れてスクリプトを叩く。定期実行と手動実行を数分以内に重ねない。両方が同じ履歴を読み、同じ告知を流しうる。

## 制約

- 同時に 2 つ走ると、同じ告知が 2 回流れうる（ロックは無く、状態はチャンネルの履歴だけ）。
- 投稿者が URL に無い投稿（`x.com/i/status/<id>`）は落とす。対象アカウントの投稿か確かめられないため。
- 要約はモデルが書く。research-x が確かめるのはアカウントと日時で、中身ではない。

## 前提

- Python 3.9 以上（標準ライブラリだけ）
- xAI の API キー。投稿するなら Slack の bot token

## テスト

```bash
bash plugins/research/tests/run-all.sh
```

オフラインで回る。xAI と Slack は `tests/fixtures/` の記録した応答で置き換える。
