# guards

Claude Code の作業を、取り返しがつかなくなる前に止めるフック集。

## フック

| フック | いつ | 何をするか |
|---|---|---|
| bash-guard | Bash の前 | ホーム・システムディレクトリへの再帰削除、未マージ worktree の削除、既定ブランチ（origin に問い合わせ、繋がらなければ手元の origin/HEAD、それも無ければ main / master）より古いブランチからの push を止める。安全領域外の削除は macOS の `trash`（ゴミ箱）なら通す |
| file-guard | Write の前 | リポ構造ルール違反の書き込み（`docs/` 直下の .md・`scripts/` 直下のスクリプトの新規作成）を止める |
| git-freshness | Bash の後・GitHub コネクタでマージした後 | マージの後、PR のマージ先ブランチをいま開いていれば `--ff-only` で最新にする（マージ先が分からなければ既定ブランチ）。できないときは知らせるだけ（止めはしない）。コネクタのマージは、手元の clone が同じリポのときだけ |

## 設定

`/plugin configure guards@shibamasa-plugins`（または `/config`）で変えられる。

| キー | 既定 | 意味 |
|---|---|---|
| `merge_allowed_repos` | 空 | **非推奨**。guards はもう読まない（0.2.0 でマージの確認を外した）。自動マージは [review](../review/README.md) の `dev-flow` に移り、リポの `.claude/dev-flow.json`（`{"autoMerge": true}`）で決める。移行が済むまでは、review のスキルがここに書いたリポも自動マージのリポとして扱う |

フックごとの調整:

- **file-guard** のルールはプラグイン同梱の [`repo-structure.md`](repo-structure.md)。`~/.claude/rules/repo-structure.md` を置くとそちらが優先、環境変数 `FILE_GUARD_SPEC` を設定するとさらに優先（存在しないパスを指せば無効化）

## マージの扱い

マージの前の確認（以前の bash-guard の merge-gate）は 0.2.0 で外した。マージの条件（レビューがそろう・`Closes` 先の `## 結果`）は review プラグインの `dev-flow` スキルと `dev-flow-gate` フックが持つ。guards だけを入れている場合、マージは止まらない。

## 前提

macOS / Linux、`python3`、`git`、`gh`

## テスト

```bash
bash plugins/guards/tests/run-all.sh
```
