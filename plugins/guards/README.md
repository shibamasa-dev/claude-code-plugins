# guards

Claude Code の作業を、取り返しがつかなくなる前に止めるフック集。

## フック

| フック | いつ | 何をするか |
|---|---|---|
| bash-guard | Bash の前 | ホーム・システムディレクトリへの再帰削除、未マージ worktree の削除、古い main からの push を止める。マージ（`git merge`・`gh pr merge`）はユーザーの確認に回す。安全領域外の削除は macOS の `trash`（ゴミ箱）なら通す |
| file-guard | Write の前 | リポ構造ルール違反の書き込み（`docs/` 直下の .md・`scripts/` 直下のスクリプトの新規作成）を止める |
| git-freshness | Bash の後 | マージや push の後、ローカル main を最新にするよう知らせる（止めはしない） |

## 設定

`/plugin configure guards@shibamasa-plugins`（または `/config`）で変えられる。

| キー | 既定 | 意味 |
|---|---|---|
| `merge_allowed_repos` | 空 | Claude の判断でマージしてよいリポ（`owner/repo` をカンマ区切り）。空ならすべてのマージをユーザーの確認に回す |

フックごとの調整:

- **file-guard** のルールはプラグイン同梱の [`repo-structure.md`](repo-structure.md)。`~/.claude/rules/repo-structure.md` を置くとそちらが優先、環境変数 `FILE_GUARD_SPEC` を設定するとさらに優先（存在しないパスを指せば無効化）

## 前提

macOS / Linux、`python3`、`git`、`gh`

## テスト

```bash
bash plugins/guards/tests/run-all.sh
```
