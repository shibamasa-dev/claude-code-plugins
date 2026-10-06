# guards

Claude Code の作業を、取り返しがつかなくなる前に止めるフック集。

## フック

| フック | いつ | 何をするか |
|---|---|---|
| bash-guard | Bash の前 | ホーム・システムディレクトリへの再帰削除、未マージ worktree の削除（置き場は問わない。リポの中の `.claude/worktrees` なども）、既定ブランチ（origin に問い合わせ、繋がらなければ手元の origin/HEAD、それも無ければ main / master）より古いブランチからの push を止める。安全領域外の削除は macOS の `trash`（ゴミ箱）なら通す。マージ済みでクリーンな worktree の削除は通す |
| repo-structure-guard | Write の前 | ルールファイルを置いたときだけ効く。リポ構成のルール違反の書き込み（`docs/` 直下の .md・`scripts/` 直下のスクリプトの新規作成）を止める |
| git-freshness | Bash の後・GitHub コネクタでマージした後 | マージの後、PR のマージ先ブランチをいま開いていれば `--ff-only` で最新にする（マージ先が分からなければ既定ブランチ）。できないときは知らせるだけ（止めはしない）。コネクタのマージは、手元の clone が同じリポのときだけ |

## 設定

`/plugin configure guards@shibamasa-plugins`（または `/config`）で変えられる。

| キー | 既定 | 意味 |
|---|---|---|
| `worktree_dirs` | 空 | worktree をまとめて置くフォルダ（カンマ区切り、例 `~/.worktrees`）。ここの配下は再帰削除を通し、未マージか判定できないパス（存在しない・変数で行き先が分からない）は止める。空でも、未マージ worktree の削除は置き場に関係なく止める |
| `shared_venv_dirs` | 空 | 複数のプロジェクトで共有する venv の置き場（カンマ区切り、例 `~/.venvs`）。ここの venv への `uv pip sync`・`uv pip install --exact`・`uv pip uninstall` を止める（定義に無い同居パッケージが消えるため）。空なら止めない |
| `merge_allowed_repos` | 空 | **非推奨**。guards はもう読まない（0.2.0 でマージの確認を外した）。自動マージは [review](../review/README.md) の `dev-flow` に移り、リポの `.claude/dev-flow.json`（`{"autoMerge": true}`）で決める。移行が済むまでは、review のスキルがここに書いたリポも自動マージのリポとして扱う |

`claude plugin install guards@shibamasa-plugins --config worktree_dirs=~/.worktrees` のように入れるときに渡してもよい。値はフックに環境変数 `CLAUDE_PLUGIN_OPTION_<KEY>`（例 `CLAUDE_PLUGIN_OPTION_WORKTREE_DIRS`）で渡る。

### リポ構成のルール（repo-structure-guard）

ルールファイルがあるときだけ効く。上から順に最初に見つかったものを使い、どれも無ければ何もしない。

1. 環境変数 `REPO_STRUCTURE_SPEC`（旧名 `FILE_GUARD_SPEC` も読む）。設定されていればこれだけを見る。存在しないパスを指せば無効
2. 書き込み先のリポの `.claude/rules/repo-structure.md`。コミットすればチームで共有でき、クラウドのセッションでも効く。Claude もルールとして読む
3. `~/.claude/rules/repo-structure.md`（自分の全リポ）

書き方の見本は [`examples/repo-structure.md`](examples/repo-structure.md)。どちらかへコピーして直す。判定に使うのは `<!-- guard:… -->` ブロックだけ。

## マージの扱い

マージの前の確認（以前の bash-guard の merge-gate）は 0.2.0 で外した。マージの条件（レビューがそろう・`Closes` 先の `## 結果`）は review プラグインの `dev-flow` スキルと `dev-flow-gate` フックが持つ。guards だけを入れている場合、マージは止まらない。

## 前提

macOS / Linux、`python3`、`git`、`gh`

## テスト

```bash
bash plugins/guards/tests/run-all.sh
```
