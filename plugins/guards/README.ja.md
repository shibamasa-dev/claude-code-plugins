# guards

[English](README.md) | 日本語

Claude Code の作業を、取り返しがつかなくなる前に止めるフック集。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install guards@shibamasa-plugins
```

## フック

| フック | いつ | 何をするか |
|---|---|---|
| bash-guard | Bash の前 | ホーム・システムディレクトリへの再帰削除、未マージ worktree の削除（置き場は問わない。リポの中の `.claude/worktrees` なども）、既定ブランチ（origin に問い合わせ、繋がらなければ手元の origin/HEAD、それも無ければ main / master）より古いブランチからの push を止める。安全領域外の削除は macOS の `trash`（ゴミ箱）なら通す。マージ済みでクリーンな worktree の削除は通す。`--json` なしの `gh issue view --comments`（コメントが 0 件の issue では何も出ない。見るのは `gh` で始まるコマンドだけで、`env gh ...` などのラッパー越しは通る）と `pip freeze`（uv の venv では空になる。`uv pip freeze` を使う（有効な環境と別の環境を対象にするなら `--python <path>` を付ける）か、頭に `PIP_FREEZE_OK=1` を付ける）も止める（gh-comments-guard・pip-freeze-guard） |
| bash-guard（publish-guard） | Bash の前、および GitHub コネクタの issue / PR 本文を書くツールの前 | `publish_patterns` を設定するまで動かない。公開しようとしている文面（タイトル・本文・本文ファイル・ヒアドキュメント）を、自分で登録した非公開値のパターンと照らす。公開リポ宛てで一致したら止め、何番目のパターンがどこで一致したかだけを伝える（一致した文字列は出さない）。非公開・internal のリポ宛ては何も出さずに通す。宛先のリポや公開範囲が分からないときは、注記を付けて通す |
| repo-structure-guard | Write の前 | ルールファイルを置いたときだけ効く。リポ構成のルール違反の書き込み（`docs/` 直下の .md・`scripts/` 直下のスクリプトの新規作成）を止める |
| git-freshness | Bash の後・GitHub コネクタでマージした後 | マージの後、PR のマージ先ブランチをいま開いていれば `--ff-only` で最新にする（マージ先が分からなければ既定ブランチ）。できないときは知らせるだけ（止めはしない）。コネクタのマージは、手元の clone が同じリポのときだけ |
| link-check | Stop（デスクトップアプリのみ） | Claude の最後の返答に、デスクトップアプリのファイルペインで開けないファイルへのリンクがあれば、1 回だけ止めて直させる。存在しないファイル（別ブランチにしか無い、基準のフォルダを取り違えた相対パスなど）と、作業ディレクトリ・追加したディレクトリ・scratchpad の外のファイルが対象。数えるのはコードの外の Markdown リンク `[label](path)` だけで、URL・`#…` のアンカー・`#fragment`・`:行番号` は扱える。`link_check=observe` なら記録するだけ |

## 設定

`/plugin configure guards@shibamasa-plugins`（または `/config`）で変えられる。

| キー | 既定 | 意味 |
|---|---|---|
| `worktree_dirs` | 空 | worktree をまとめて置くフォルダ（カンマ区切り、例 `~/.worktrees`）。ここの配下は再帰削除を通し、未マージか判定できないパス（存在しない・変数で行き先が分からない）は止める。空でも、未マージ worktree の削除は置き場に関係なく止める |
| `publish_patterns` | 空 | publish-guard を有効にする。正規表現の JSON 配列を 1 行で書く（例 `["acme-internal", "(?i)acme-[a-z]+-private"]`）。issue / PR の文面を公開する前に 1 行ずつ照らす。大文字小文字を区別しないときはパターンに `(?i)` を書く。sensitive な値として保存される（`settings.json` ではなく OS の資格情報ストア）。`/config` には出ないので、`/plugin configure guards@shibamasa-plugins` で設定するか、入れるときに `--config 'publish_patterns=["acme-internal"]'` で渡す。JSON 配列でない値のときはチェックせず注記を出す。正規表現として読めない要素は飛ばし、何番目かを伝える |
| `link_check` | `enforce` | link-check の動き方。`enforce` は返答ごとに 1 回止める。`observe` は検出を `${CLAUDE_PLUGIN_DATA}/link-check/`（変数が無いときは `~/.claude/state/guards/link-check/`）の日ごとのファイルに追記するだけ（時刻・セッション ID・対象。30 日残す）。`off` は何もしない |

`claude plugin install guards@shibamasa-plugins --config worktree_dirs=~/.worktrees` のように入れるときに渡してもよい。値はフックに環境変数 `CLAUDE_PLUGIN_OPTION_<KEY>`（例 `CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS`）で渡る。

### publish-guard が読むもの

- コマンド: `gh issue create|edit|comment`、`gh pr create|edit|comment|review`、`--comment` 付きの `gh issue|pr close|reopen`、書き込みメソッドの `gh api`（`-X POST|PATCH|PUT`、または `-f` / `-F` / `--input` があるもの）で `repos/<owner>/<repo>/` の下の issue・コメント・プルリクエスト・レビュー・レビューコメントのエンドポイントを叩くもの、`gh api graphql`（すべてのフィールド値）
- 文面: `--title` / `-t`、`--body` / `-b`、`--body-file` / `-F` のファイル、`gh api` の `title` / `body` フィールド（`comments[][body]` のような入れ子、`-F body=@file`、`--input <file>` の JSON に含まれるすべての文字列（デコードしたもの）を含む）、同じコマンドの中のヒアドキュメントの中身すべて、`$(cat <file>)` や `$(< file)` で読むファイル。ファイルのパスそのものは見ない
- コネクタのツール（サーバー名に関係なく、ツール名の末尾で判定）: `issue_write`、`add_issue_comment`、`update_issue_comment`、`create_pull_request`、`update_pull_request`、`pull_request_review_write`、`add_comment_to_pending_review`、`add_reply_to_pull_request_comment` の `title` と `body`、加えて `labels` と issue フィールドの値
- 宛先のリポ（一致したときだけ調べる）: 引数に渡した issue / PR の URL、`-R` / `--repo`、`gh api` の `repos/<owner>/<repo>/`、`GH_REPO`、コマンドを実行するフォルダの `gh-resolved` が付いた remote、無ければそのフォルダにただ 1 つある GitHub の remote、の順。公開範囲は `gh api --hostname github.com repos/<owner>/<repo>`（5 秒）で聞き、プラグインのデータフォルダに覚えておく（`public` は 7 日、それ以外は 1 時間）。非公開として覚えたあとに公開されたリポは、最長 1 時間守られない
- 同じコマンドの中で `gh` より前に書く本文ファイルは、フックが書き込みと分かるもの（`>`、`>>`（元の中身へ足す）、`tee`、ヒアドキュメント、`cp`、`mv`、`install`、`sed -i`、`dd of=`）であれば、ディスク上の中身では判定しない（それはコマンドを実行する前のもの）。書く文面がコマンドに書いてあれば（ヒアドキュメント、`echo` や `printf` の引数）それをチェックする。そうでなければ注記を付けて通し、ファイルを前のコマンドで書くよう伝える

### リポ構成のルール（repo-structure-guard）

ルールファイルがあるときだけ効く。上から順に最初に見つかったものを使い、どれも無ければ何もしない。

1. 環境変数 `REPO_STRUCTURE_SPEC`。設定されていればこれだけを見る。存在しないパスを指せば無効
2. 書き込み先のリポの既定ブランチ（`origin/<既定>`）にある `.claude/rules/repo-structure.md`。コミットすればチームで共有でき、クラウドのセッションでも効く。Claude もルールとして読む。作業ツリーではなく既定ブランチから読むので、新しいルールや変えたルールはマージし、ローカルの `origin/<既定>` を fetch してから効き、それまでは次の候補が使われる。`origin` リモートが無いリポは作業ツリーを読む
3. `~/.claude/rules/repo-structure.md`（自分の全リポ）

書き方の見本は [`examples/repo-structure.md`](examples/repo-structure.md)。どちらかへコピーして直す。判定に使うのは `<!-- guard:… -->` ブロックだけ。

### ファイルの置き場

プラグインが書くのは 2 つで、どちらも `${CLAUDE_PLUGIN_DATA}`（`~/.claude/plugins/data/<プラグイン ID>/`）の中。publish-guard の公開範囲のキャッシュ `repo-visibility.json` と、`link_check=observe` のときだけ link-check の日ごとの記録 `link-check/`（30 日を過ぎたファイルは次の記録のときに消す）。最後の scope からアンインストールすると両方消える（`--keep-data` を付ければ残る）。消えてもフックが GitHub に聞き直すので困らない。repo-structure-guard はクローンごとに git common dir に小さなファイルを 2 つ置き、アンインストールしても残る。`repo-structure-guard-origin-miss`（更新時刻が最後に `origin` に届かなかった時刻）と `repo-structure-guard-origin-head`（origin が最後に答えた既定ブランチと、そのときのコミット）。

## マージの扱い

マージの前の確認（以前の bash-guard の merge-gate）は 0.2.0 で外した。マージの条件（レビューがそろう・`Closes` 先の `## Result`）は workflow プラグインの `dev-flow` スキルと `dev-flow-gate` フックが持つ。guards だけを入れている場合、マージは止まらない。

## 限界

guards は Claude の誤操作を減らすための安全網で、悪意のある操作を止めるサンドボックスではない。フックが解析できない形で組み立てたコマンドは通ることがある。

既定ブランチから設定を読むチェック（repo-structure-guard）が防ぐのは、ブランチの中身（コミットしたファイル・push したブランチ）で変えられるものまで。手元の git の設定と環境変数は信頼し、既定ブランチは `origin` のものを正とする。fork で作業する場合は `upstream` ではなく fork の既定ブランチになる。origin の既定ブランチが分からないとき（使える手元の `origin/HEAD` が無く、origin にも届かない）、チェックは動かず、その旨を出し、origin に聞き直すのは 1 時間以上あとになる。手元の `origin/HEAD` は、origin が認めたあと、それが指すブランチが動いていない間はネットワークに出ずに使う。fetch でそのブランチが動くと（たとえば既定ブランチの改名後に、古い名前でブランチが push されたとき）、次の呼び出しで origin に一度聞く。そのとき origin に届かないか、同じチェックのネットワーク処理が過去 1 時間以内に失敗していれば手元の答えを使い続けるので、origin が答えるまでは、古い既定ブランチの名前で push されたブランチが設定を与えうる。部分クローン（partial clone）で設定ファイルの中身が手元に無いときは 5 秒以内で取りにいき、失敗したら読めない扱いにして、取り直すのは 1 時間以上あとになる。プロジェクトの `.claude/settings.json` はプラグインを無効にでき（`enabledPlugins`）、セッションの環境変数も設定できる（`env`）。このファイルを変える PR は人が差分を見る必要がある。止められるのは managed settings だけ。

publish-guard が捕まえるのは、コマンドの文面に書かれた非公開値で、実行して初めて現れる値は捕まえない。次のものは見えない。

- 実行時に作られる文面: 前の呼び出しで代入した変数、`$(python …)`、`jq`、`printf` のエスケープ、base64
- 別のプログラムからパイプで渡す本文（`… | gh issue create --body-file -`）。文面を見ていないという注記を付けて通す
- `curl` で API を叩くもの、ほかの公開コマンド（`gh release`、`gh gist`、`gh repo edit --description`、wiki、discussions、コミットメッセージ）、`gh pr create --fill`（コミットの文面）、`--web`
- ツール名が上の一覧と違うコネクタ
- 見た目が似た別の文字（全角英字・ホモグリフ）、パターンに `(?i)` が無いときの大文字小文字違い
- `gh` とコマンドグループの間に書いたフラグ（`gh -R owner/repo issue create`）、ほかと束ねた短いフラグ、前もって `export GH_REPO=…` で決めたリポ（読むのはコマンド自体に付けた `GH_REPO=… gh …` だけ）
- ヒアストリング（`<<<`）、ファイルからリダイレクトした本文（`--body-file - < file`）
- `gh api graphql` の書き込み先（宛先をリポ名ではなく node id で指す）、GitHub の remote が複数あって既定の印が無いフォルダで `gh` が選ぶリポ。ここで一致したときは注記を付けて通す

判定できないもの（宛先のリポ・公開範囲・ファイル）は止めずに、注記を付けて通す。公開された文面を CI で調べる仕組みが後ろの備えになる。

ほかに知っておくこと。

- 公開する `gh` を含むコマンドでは、その中のヒアドキュメントと `$(cat file)` はすべて、別の用途のものでも公開される文面として扱う。それで止まったら、コマンドを 2 つに分ける
- 本文ファイルへの書き込みは、コマンドのどこにあっても実行されるものとして扱う。シェルが飛ばす書き込み（`false && echo … > f`）があるとディスク上の中身はチェックされず、`gh` より後ろの書き込みは `gh` が読むものとしてチェックする。本文ファイルは前のコマンドで書くこと
- 引用符を含む `echo` / `printf` は、書き込み先のファイル名を含むすべての語を、書く文面として扱う
- 同じコマンドの中でそれ以外の方法で本文ファイルを書いた場合（パスを受け取るスクリプトやプログラム、`python -c`、`ln`、`rsync`、`curl -o`、関数や `eval` の中のリダイレクト）は分からない。コマンド実行前のディスク上の中身で判定する
- リポの `owner/name` 自体がパターンに一致する場合、deny や注記の文面にその名前が出る（コマンドラインにすでに書かれている名前）
- パターンは書いたとおりに、時間の上限なしで動く。バックトラックが爆発するパターンはフックを止め、フックがタイムアウトすると、その呼び出しでは bash-guard のほかのルールの判定も失われる。パターンは単純に保つ（名前そのもの、短い選択肢）
- 公開範囲の問い合わせに失敗したことは 1 時間覚えておく。その間、そのリポ宛ての一致は注記を付けて通る
- 公開範囲のキャッシュ（プラグインのデータフォルダの `repo-visibility.json`）には、一致があったリポの名前が、非公開のものも含めて平文で入る
- `publish_patterns` が JSON として読めないことは、公開するコマンドを実行したときにだけ伝える
- ガードが無効でも、GitHub コネクタの書き込みツールの前にはフックが起動する（数十ミリ秒。何もしない）

link-check:

- 追加したディレクトリは Stop フックの入力に無いので、セッションのトランスクリプトの `environment` の項目から読む（公開された形式ではない）。その項目（または scratchpad のパス）が無いときは、作業ディレクトリの外に実在するファイルへのリンクは通し、存在しないファイルだけを止める
- 見るのはターンの最後の返答だけ（Stop の入力にそれより前の文は無い）で、Markdown リンクだけ。バッククォートで囲んだだけのパスは見ない
- 見るのはファイルがあるかどうかで、意図したファイルへのリンクかどうかは分からない
- `CLAUDE_CODE_ENTRYPOINT` が `claude-desktop` のときだけ動く。デスクトップのセッションから起動した `claude -p` はこの値を引き継ぐので、そこでも動く

## 前提

macOS / Linux、`python3`、`git`、`gh`

## テスト

```bash
bash plugins/guards/tests/run-all.sh
```
