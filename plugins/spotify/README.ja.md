# spotify

[English](README.md) | 日本語

自分の Spotify を Web API で操作するスキル群。端末を選んで再生する、再生を別の端末へ移す、今流れている曲と最近聴いた曲を見る、自分のプレイリストを読む、重複させずに曲を足す、♡（Liked Songs）を確かめる。プレイリストから好みを読んで Claude が曲を選んで流し、気に入った曲をプレイリストに足す流れも回せる。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install spotify@shibamasa-plugins
```

入れたら Claude に「Spotify を使えるようにして」と頼む。残りは `setup` スキルが案内する。

## スキル

| スキル | 使いどころ |
|---|---|
| `spotify` | 「Spotify で〜かけて」「おすすめ流して」「今なに流れてる？」「スマホで再生して」「このプレイリストに足して」。コマンドは `devices`・`play`・`transfer`・`now`・`recent`・`playlists`・`tracks`・`taste`・`search`・`add`（既に入っている曲は足さない）・`liked`・`check`・`auth`。実体は `skills/spotify/scripts/spotify.py`（Python・標準ライブラリだけ）で、JSON を出し、トークンは出さない。おすすめは Claude が `taste` を読んで自分で選び（Spotify の `/recommendations` は新しいアプリでは使えない）、再生し、あとで♡を付けた曲だけを足す |
| `setup` | 初回の準備と許可のやり直し。Spotify の開発者アプリを作り（Redirect URI は `http://127.0.0.1:<redirect_port>/callback`、Web API を選ぶ）、鳴らす端末で Spotify アプリを開き、自分の Client ID で最初のブラウザ許可を行い、`check` と `devices` で確かめる |

## 認証の仕組み

Authorization Code + PKCE なので、Client Secret はどこにも使わない。`auth` がブラウザで Spotify の同意画面を開き、`127.0.0.1:<redirect_port>` で callback を待つ。受け取った client ID・refresh token・access token をトークンの置き場に入れる。access token は 1 時間で切れ、切れたときだけスクリプトが更新し、Spotify が新しい refresh token を返したらそれも書き戻す。新しいトークンを Spotify に頼む前に置き場へ書けるかを確かめるので、差し替わった refresh token を受け取ったまま失うことはない。

refresh token は開発者アプリの「Refresh Token Lifetime」の日数で切れる。切れるとコマンドが `invalid_grant` で失敗するので、`setup` スキルで `auth` をやり直す。

## 設定

| キー | 既定 | 意味 |
|---|---|---|
| `token_store` | `file` | client ID とトークンの置き場。`file` は JSON ファイル 1 つ（権限 0600、ディレクトリは 0700）。`1password` は 1Password の項目 1 つで、`op` CLI で読み書きする |
| `op_item` | `Spotify Web API` | 1Password の項目のタイトル（`1password` のときだけ）。最初の `auth` が作る |
| `op_vault` | 空 | その項目の vault（`1password` のときだけ）。空なら、読むときは全 vault、作るときは `op` の既定の vault |
| `redirect_port` | `8888` | 開発者アプリに登録した Redirect URI のポート。変えるときは両方そろえる |

Claude が Bash で動かすコマンドにはこれらの値が自動では渡らないので、スキルが環境変数でスクリプトに渡す。`${user_config...}` のまま置き換わっていない値は未設定とみなし、既定を使う。

### ファイルの置き場所

| ファイル | 場所 | 中身 |
|---|---|---|
| `token.json` | `${CLAUDE_PLUGIN_DATA}/spotify/` | client ID・refresh token・access token とその期限（`file` のとき）。同じディレクトリの一時ファイルに書いてから名前を付け替える |

`${CLAUDE_PLUGIN_DATA}` は `~/.claude/plugins/data/spotify-<marketplace>/`。`CLAUDE_PLUGIN_DATA` がこのプラグインのディレクトリでないとき、スクリプトは `file` の置き場を使わずに止まる（トークンを別の場所に書いて 2 か所に分かれないようにするため）。`1password` のときはディスクに何も書かない。

プラグインを最後に入っている場所からアンインストールすると、`--keep-data` を付けない限り `${CLAUDE_PLUGIN_DATA}` ごとトークンが消える。1Password の項目は消えないので、要らなければ自分で消す。許可そのものを取り消すには https://www.spotify.com/account/apps/ でアプリを外す。

## 制限

- 使えるのは自分のアカウントだけ。開発者アプリは Development Mode で、アプリの持ち主が Spotify Premium であることが要り、利用者は 5 人まで。
- 再生の操作（`play`・`transfer`）は Premium だけ。鳴らせるのは Spotify アプリが開いている端末だけ。
- 読めるのも足せるのも、自分のプレイリストと共同編集のものだけ。曲を消すコマンドは無い。
- `/recommendations`・関連アーティスト・音響特徴は使えない（2024-11-27 以降に作ったアプリには Spotify が閉じた）。曲は Claude が選ぶ。
- 「気に入った」は♡を付けたかどうか。最後まで聴いたかは使わない。
- Claude Code の Bash サンドボックスの中では `op` が動かず、トークンファイルへの書き込みも止められることがある。スキルはそのコマンドをサンドボックスの外で動かすよう Claude に指示している。
- Spotify のリファレンスから模擬しているが、まだ実アカウントで確かめていない挙動がある: ♡の並び順、今再生中の 204、再生エラー 404・403 の reason 名（`skills/spotify/references/api-notes.md`）。

## 前提

- Spotify Premium のアカウント（開発者アプリの持ち主）
- Python 3.9 以上（標準ライブラリだけ）
- `auth` 用に、同じマシンのブラウザ
- `1password` の置き場を使うときだけ、1Password CLI（`op`）とデスクトップアプリとの連携

## テスト

```bash
bash plugins/spotify/tests/run-all.sh
```

オフラインで動く。どのケースも 127.0.0.1 の模擬 Spotify と一時的なプラグインのデータディレクトリに向けてスクリプトを動かし、`PATH` には記録用の `op` スタブとシステムのディレクトリしか入れないので、本物の Spotify にも 1Password にも届かない。確かめるのは、端末名での再生と切り替え、重複を除いて 100 曲ずつ足すこと、あいまいな名前や他人のプレイリストを断ること、指定時刻以降の♡、トークンを出さずに更新して書き戻すこと、再生のエラーと 429 の再試行、`taste`、PKCE の `auth`（state 違いを断り、トークンを保存し、保存したトークンで `check` が通る）、umask 022 の下で `token.json` が 600・ディレクトリが 700 になること、`1password` の置き場が項目の JSON を stdin で渡して `op` を呼ぶこと、置き換わっていない `${user_config...}` が `file` の置き場になること、別のプラグインのものや置き換わっていない `CLAUDE_PLUGIN_DATA` を断ること、知らない `token_store`、置き場に書けないときに更新の前で止まること。
