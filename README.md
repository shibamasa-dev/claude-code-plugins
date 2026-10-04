# claude-code-plugins

Claude Code 用のプラグインマーケットプレイス。日々の開発で使っているガード・運用スキルを、汎用にして公開したもの。スキルの本文とメッセージは日本語。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install guards@shibamasa-plugins
/plugin install workflow@shibamasa-plugins
/plugin install docs@shibamasa-plugins
```

3 本は独立していて、必要なものだけ入れられる。

## プラグイン

### guards — 作業を止めるフック

| フック | いつ | 何を止めるか |
|---|---|---|
| bash-guard | Bash の前 | ホーム・システムディレクトリへの再帰削除、未マージ worktree の削除、未検証のマージ（確認を出す）、古い main からの push。安全領域外の削除は macOS の `trash`（ゴミ箱）なら通す |
| file-guard | Write の前 | リポ構造ルール違反の書き込み。ルールは `~/.claude/rules/repo-structure.md`（`FILE_GUARD_SPEC` で変更可）。無ければ何もしない |
| full-test-gate | セッション開始・Bash の前 | 全体テストを最後に通してからの変更量を知らせ、リリース等のコマンドを未検証の変更があれば止める。対象はリポに `.claude/full-test.json` を置いたプロジェクトだけ |
| git-freshness | Bash の後 | マージや push の後、ローカル main を最新にするよう知らせる（止めはしない） |

設定（`/plugin configure guards`）:
- `merge_allowed_repos` — Claude の判断でマージしてよいリポ（`owner/repo` をカンマ区切り）。既定は空で、すべてのマージをユーザーの確認に回す

### workflow — issue・PR・セッション運用

スキル: `issue-ops`（issue の起票〜close の規約）／`pr-review-wait`・`pr-rereview`（CodeRabbit・Codex のレビュー待ちと再レビュー）／`session-wrap`（閉じる前の残件確認）／`codebase-doctor`／`context-diet`／`remote-setup`／`weekly-orchestrator-base`／`openapi-to-skills`／`testcase-generator`

フック: `handoff`（セッションをまたぐ次の入口）／`issue-writeback`（読んだ issue に決定を書き戻させる）／`runbook`（ブラウザ・画面操作の手順を記録）／`knowledge-freshness`（スキルの鮮度切れを知らせる）／`artifact-ledger`（公開した Artifact をプロジェクトに記録）／`testcase-lint`

コマンド: `/workflow:dev-process:review-and-fix`

組織の値（GitHub 組織・既定リポ・Issue Fields・プロジェクトボード）はスキルに持たない。セッション文脈に「組織設定」という見出しの注入テキストがあればそれを、無ければプロジェクトの CLAUDE.md を読む。社内向けの値は別のプラグインから SessionStart フックで注入する想定。

### docs — 画像・動画

スキル: `image-generation-prompt`（画像生成の指示文を構造化）／`motion-video`（コードで描くモーショングラフィックス動画）

フック: `design-lint`（DESIGN.md を編集したら lint）

## 前提

- macOS / Linux、`python3`、`git`、`gh`
- `motion-video` は Node.js・Chrome・ffmpeg、`openapi-to-skills` は `uv`

## コントリビュート前の確認

コミット前に、個人環境（ホームの絶対パス・メールアドレス）の混入とコミット作者のメールを検査するフックを同梱している。clone ごとに 1 回（フックを更新したときも）、中身を確認してから入れる:

```bash
bash .githooks/install.sh
```

`origin/main` のフックと検査スクリプトを `.git/hooks/` にコピーして使う（作業ツリーのファイルを直接実行しないので、外部の PR ブランチを checkout してもそのコードは走らない）。`install.sh` 自体は作業ツリーから実行されるので、main を checkout した状態で中身を確認してから実行する。既に別の場所のフック（グローバルの `core.hooksPath` 等）を使っていれば、そこには書き込まず、検査のあとに続けて呼ぶ。

追加で止めたい固有名があれば `~/.config/claude-code-plugins/blocked-patterns` に 1 行 1 正規表現で書く（リポには置かない）。同じ検査は CI（`.github/workflows/`）でも走る。


## ライセンス

MIT
