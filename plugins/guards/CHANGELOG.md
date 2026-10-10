# Changelog

guards プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.4.0] - 2026-10-10

特定の運用を前提にした決め打ちを外し、使う人が選べるようにした。**今までの挙動に頼っていた場合は、下の「戻し方」を見てほしい。**

### Changed
- file-guard を repo-structure-guard（`hooks/repo-structure-guard.py`）に改名し、オプトインにした。ルールファイルがあるときだけ効く。探す順は環境変数 `REPO_STRUCTURE_SPEC`（旧名 `FILE_GUARD_SPEC` は読まない）→ 書き込み先のリポの `.claude/rules/repo-structure.md` → `~/.claude/rules/repo-structure.md`。リポごとにルールを変えられ、コミットすればチームやクラウドのセッションでも効く
- 同梱のルール `repo-structure.md` は `examples/repo-structure.md` に移した。見本としてだけ置き、フックは読まない
- `~/.worktrees` の特別扱いを外し、設定 `worktree_dirs`（既定は空）にした。書いたフォルダは今までの `~/.worktrees` と同じ扱い（配下の再帰削除を通し、未マージか判定できないパスは止める）
- rm-guard は、マージ済みでクリーンな linked worktree の root の削除を置き場に関係なく通す（`worktree_dirs` が空でも、片付けのたびに確認が出ないように）
- shared-venv-guard は設定 `shared_venv_dirs`（既定は空）に書いた置き場にだけ効く。空なら止めない。`~` の形・`$HOME` の形・絶対パスのどれで書いたコマンドも見る。`uv pip` 自身か、その時点で有効な venv（`source …/activate`・`export VIRTUAL_ENV=…`）または今いるフォルダ（`cd`）が置き場を指すときだけ止める。`--python` で置き場の外を明示したら止めない
- 設定値はフックが環境変数 `CLAUDE_PLUGIN_OPTION_<KEY>` から読む（シェル形式のフックのコマンドには `${user_config.KEY}` を書けないため）

### 戻し方
- 環境変数 `FILE_GUARD_SPEC` を使っていた場合：`REPO_STRUCTURE_SPEC` に名前を変える
- リポ構成のルール：`examples/repo-structure.md` を `~/.claude/rules/repo-structure.md`（全リポ）か `<repo>/.claude/rules/repo-structure.md`（そのリポだけ）にコピーする
- worktree の置き場・共有 venv：`/plugin configure guards@shibamasa-plugins`（または `/config`）で `worktree_dirs` に `~/.worktrees`、`shared_venv_dirs` に `~/.venvs` を入れる。`claude plugin install --config worktree_dirs=~/.worktrees` でもよい

## [0.3.1] - 2026-10-10

### Changed
- README と bash-guard のコメントの dev-flow の置き場を workflow プラグインに直した

## [0.3.0] - 2026-10-10

### Removed
- 非推奨の設定 `merge_allowed_repos` を消した。自動マージのリポはリポの `.claude/dev-flow.json`（`{"autoMerge": true}`）で示す

## [0.2.2] - 2026-10-06

### Fixed
- bash-guard（worktree-guard）：`~/.worktrees/` の外にある worktree（Claude Code 標準の `<repo>/.claude/worktrees/` など）も、未マージなら `rm -rf`・`trash`・`find -delete` での削除を止める。消す先が linked worktree そのものか、それを含む上位のフォルダかを `git worktree list` で見る。worktree の中のサブパスの掃除はこれまでどおり通す。`{a,b}`・`{1..3}` のブレース展開はシェルと同じく展開し、`*` などの glob はシェルの設定（dotglob・nocaseglob・extglob）で当たりうるものを広めに集めてから見る（引用符で囲んだ `[`・`{` などの文字どおりのパスも見る。展開が 256 を超えたら確かめきれないとして止める。globstar の `**` は `**` の手前のフォルダから下を見る）。`find -L`・`-follow` はシンボリックリンクの先も、`find -H` は開始パスのリンクの先を見る。`$TMPDIR`・`${TMPDIR:-…}` の下は、フックが受け継いだ TMPDIR で行き先を確かめる（分からなければ止める）。消す先の中の `.git` ファイルも探す（git の管理下でないフォルダや、関係ないリポの中にある worktree も拾う）。深さでは打ち切らず、見るフォルダがコマンド全体で 20000 を超えたら（glob の一致が 256 を超えたときも）確かめきれないとして止める（読めないフォルダがあったときも。`.git` と `node_modules` の中は見ない）。条件付きの `find … -delete`（`-name '*.pyc'` など）は worktree を丸ごと消せないので対象にしない。守るのは worktree の丸ごとの削除で、worktree の中のファイルを消すこと（サブパスの削除・条件付きの find）は対象外
- worktree-guard が消す先を調べる git は、フックが受け継いだ `GIT_DIR`・`GIT_WORK_TREE` などを外して、そのフォルダのリポで動かす（別のリポの値で未マージ worktree を見逃さない）。push・commit 前の鮮度チェックは、実行されるコマンドと同じく受け継いだ値のまま見る
- worktree-guard のメッセージの「main 取り込み済みなら」を「既定ブランチに取り込み済みでクリーンなら」にした

## [0.2.1] - 2026-10-06

### Fixed
- git-freshness：マージの後に追従させるブランチを main 固定から PR のマージ先にした。GitHub コネクタは返ってきたマージコミットが今のブランチの origin に入っていれば追従、`gh pr merge` は `gh pr view` の baseRefName（取れなければ既定ブランチ）。`-R` で別リポを指したときは動かない
- bash-guard：push 前と commit 前の鮮度チェック、worktree 削除時の未マージ判定の基準を main 固定から既定ブランチ（origin/HEAD、無ければ main / master）にした
- フックのメッセージから特定の運用（スケジューラ）を前提にした書き方を外した
- 既定ブランチは origin に問い合わせて決める（`git ls-remote --symref`、読むだけ）。繋がらなければ手元の origin/HEAD、それも無ければ main / master。手元の origin/HEAD は fetch で更新されず、origin 側で既定を変えると古いままになるため。commit 前のチェックだけは通信せず手元の値を使う
- git-freshness：`gh pr merge` の `-R` のホスト付きの形（`github.com/OWNER/REPO`）と、PR の URL を指定したときも、手元の origin と同じリポかを確かめる。ホストを省いた `-R OWNER/REPO` は owner/repo だけで比べる（GitHub Enterprise の clone でも動く）
- `git fetch` に渡すブランチ名の前に `--` を置き、`-` で始まる名前がオプションとして読まれないようにした
- git-freshness：マージ先のブランチを開いているのに origin と比べられなかったとき（オフラインなど）、黙らずにそう伝える

## [0.2.0] - 2026-10-06

### Removed
- bash-guard のマージ前の確認（merge-gate）を外した。マージの条件は review プラグインの `dev-flow` スキルと `dev-flow-gate` フックへ移した。guards だけを入れている場合、マージは止まらない
- 設定 `merge_allowed_repos` を非推奨にした。guards はもう読まない。自動マージはリポの `.claude/dev-flow.json`（`{"autoMerge": true}`）へ移す

### Changed
- git-freshness：GitHub コネクタでマージした後（`merge_pull_request`）も、手元の clone が同じリポならローカル main を追従させる

## [0.1.5] - 2026-10-06

### Removed
- `full-test-gate` を testing プラグインへ移した。引き続き使うには testing プラグインを入れる

## [0.1.4] - 2026-10-06

### Added
- プラグインの README

### Changed
- plugin.json に `homepage`・`repository`・`keywords` を追加

## [0.1.3] - 2026-10-06

### Fixed
- bash-guard のマージ前ゲート：前のセグメントで設定・export した `GH_REPO` や `-R`・URL も見て対象リポを決める。決めきれないときは例外にしない
- bash-guard：sudo・env・timeout などのラッパーの長いオプションや短いオプションの束も読んで、中のコマンドを判定する
- bash-guard の削除ガード：開始パスを省いた `find` はカレントからとして扱い、条件なしでカレントを消す `find` は `rm -rf .` と同じ扱いにする。`-exec`・`-ok` が実行するコマンドも判定する
- bash-guard：演算子つきの変数展開（`${NAME:-word}` など）と、子シェルの中の外側の変数は判定不能（安全側）にする
- bash-guard：`if`・`while`・`for`・`case` の中の cd・代入は、実行されるか分からないものとして扱う

## [0.1.2] - 2026-10-05

### Changed
- file-guard の規約ファイル `repo-structure.md` をプラグインに同梱し、既定にした。`~/.claude/rules/repo-structure.md` があればそちらが優先
- file-guard の skills 例外を、リポ相対パスで `scripts/` 直下のものだけに限定した

## [0.1.1] - 2026-10-04

- 公開リポでの初版（bash-guard・file-guard・full-test-gate・git-freshness）
