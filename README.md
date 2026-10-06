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

| プラグイン | 中身 |
|---|---|
| [guards](plugins/guards/README.md) | 作業を止めるフック。破壊的な削除・未検証のマージ・古い main からの push・リポ構造違反の書き込み |
| [workflow](plugins/workflow/README.md) | issue 運用・PR レビュー待ち・セッションの引き継ぎ・runbook 記録・テスト設計などのスキルとフック |
| [docs](plugins/docs/README.md) | 画像生成プロンプト・コードで描くモーション動画のスキル |

スキル・フックの一覧と設定は、各プラグインの README にある。

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
