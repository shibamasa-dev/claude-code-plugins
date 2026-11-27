# personal-knowledge

[English](README.md) | 日本語

個人のデータを手元のマシンに貯めるスキル群。今は `get-chrome-history` の 1 つだけ。Chrome の閲覧履歴を読んで興味の傾向をまとめ、実行するたびに使っているサイトを少しずつ覚えていく。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install personal-knowledge@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `get-chrome-history` | 「ブラウザ履歴を分析して」「最近何を見てるか教えて」「閲覧傾向を教えて」。Claude が前回以降に増えた訪問を読み、サービスごと（動画・コード・ドキュメント・音楽・買い物・ニュース・SNS）にまとめ、まだ知らないドメインを分類し、傾向を JSON で返す。ユーザープロフィールやおすすめの材料に使える。実体は `skills/get-chrome-history/scripts/get_chrome_history.py`（Python・標準ライブラリだけ） |

## get-chrome-history の動き

1. **読む。** `chrome_profile` のプロファイルの History データベースを、`~/Library/Application Support/Google/Chrome/<profile>/`（macOS）、`~/.config/google-chrome/<profile>/`・`~/.config/chromium/<profile>/`（Linux）から探す。Chrome は起動中このファイルをロックするので、一時ディレクトリにコピーして読み、コピーは消す。Chrome のファイルには書かない。
2. **範囲。** そのプロファイルで前回見た一番新しい訪問より後の訪問を取る。プロファイルごとの初回は直近 7 日。
3. **振り分ける。** 訪問ごとに 3 つのどれかに入れる: `knowledge.json` にある既知のサービス（カテゴリ付き）、未知のドメイン（集計し、タイトルの例を付け、滞在時間の多い順に上位 20 件）、ノイズ（`min_visit_duration_seconds` より短い、`min_visit_count` より訪問が少ない、または `"ignore": true` を付けたサービス）。
4. **覚える。** Claude が未知のドメインを分類して自分の `knowledge.json` に足すので、次の実行から既知になる。
5. **まとめる。** Claude がカテゴリごとの傾向を利用者の言語でまとめる。根拠が薄い項目は空のままにする。

ページのタイトルは訪れたサイトが書いたものなので、スクリプトは制御文字を除いて 200 文字で切り、スキルはタイトルや URL の中の指示に従わないよう Claude に指示している。プラグインが保存するファイル（`knowledge.json`・`state.json`）は手元のマシンに残る。スクリプトが出力した履歴はそうではない。Claude との会話に入るので、範囲内の訪問の URL とタイトルは、セッションのほかの内容と同じくモデルの提供元へ送られる。あとで要約しても送られた事実は消えない。それでよいときだけスキルを使うこと。スキルは、生の URL やタイトルをよそに書くファイルやメッセージへ写さないよう Claude に指示している。

## 設定

| キー | 既定 | 意味 |
|---|---|---|
| `chrome_profile` | `Default` | 読む Chrome のプロファイルのディレクトリ名（`Default`・`Profile 1` など）。空なら `Default`。そのプロファイルに History が無いときは、見つかったプロファイルを示す |

プロファイルのディレクトリ名は、そのプロファイルで `chrome://version` を開くと、プロファイルのパスの行の末尾に出ている。

### ファイルの置き場所

| ファイル | 場所 | 中身 |
|---|---|---|
| `knowledge.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | スキルが知っているサービスとフィルタ。初回に `skills/get-chrome-history/knowledge.json` の種をコピーし、以後は Claude が自分のコピーに足していく。プラグインを更新しても上書きしない |
| `state.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | 見た中で一番新しい訪問の時刻。History ファイルごとに持つので、`chrome_profile` を切り替えても取りこぼさない。消すと次は直近 7 日を取り直す |
| History のコピー | システムの一時ディレクトリ | 読み終えたらすぐ消す |

`${CLAUDE_PLUGIN_DATA}` は `~/.claude/plugins/data/personal-knowledge-<marketplace>/`。これが無い状態で動いたとき（ターミナルから手で動かしたときなど）は、代わりに `~/.claude/state/personal-knowledge/get-chrome-history/` を使い、そのことを標準エラーに出す。

プラグインを最後に入っている場所からアンインストールすると、`--keep-data` を付けない限り `${CLAUDE_PLUGIN_DATA}` ごと `knowledge.json` と `state.json` が消える。`~/.claude/state/` の代わりの置き場所は消えない。

## 制限

- 読めるのは macOS と Linux の Chrome・Chromium だけ。Windows、ほかの Chromium 系ブラウザ（Edge・Brave・Arc）、Firefox は読まない。
- 1 回に読むのは 1 プロファイル。
- サービスはホストとその親ドメインで照合する（`www.amazon.co.jp` は `amazon.co.jp` に当たる）。パスでは見ないので、同じホストにある 2 つのサービスは区別できない。
- 範囲は URL ごとの最終訪問時刻で決まる。URL の `visit_count` と滞在時間は Chrome に残る累計で、範囲内の分だけではない。
- コピーは Chrome が書き込み中かもしれない時点で取る。コピーの時点で Chrome がまだ確定していなかった訪問は、それより新しい訪問がコピーに入っていると取りこぼす。

## 前提

- Google Chrome か Chromium
- macOS か Linux
- Python 3.9 以上（標準ライブラリだけ）

## テスト

```bash
bash plugins/personal-knowledge/tests/run-all.sh
```

オフラインで動く。どのケースも、Chrome の `urls` / `visits` テーブルと架空の URL で History データベースを一時ディレクトリに作り、`HOME`・`TMPDIR`・`CLAUDE_PLUGIN_DATA` をそこへ向けるので、本物のプロファイルやホームディレクトリは読み書きしない。確かめるのは、3 つの振り分け、初回の 7 日の範囲、差分の取得、プロファイルごとのカーソル、読めない History のコピー、初回の実行がデータディレクトリの `knowledge.json` と `state.json` だけを書く（スキルのディレクトリには何も書かない）こと、種のコピーが 1 回だけで上書きされないこと、代わりの置き場所、プロファイルが無いとき、Linux のプロファイルの場所、ASCII のロケールでの出力（プロファイルが無いときのエラーも）、出力を書けなかった実行が `state.json` を書かないこと、タイトルの整形。
