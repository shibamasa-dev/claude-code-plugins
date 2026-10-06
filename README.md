# claude-code-plugins

[![ci](https://github.com/shibamasa-dev/claude-code-plugins/actions/workflows/ci.yml/badge.svg)](https://github.com/shibamasa-dev/claude-code-plugins/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Claude Code 用のプラグインマーケットプレイス。日々の開発で使っているガード・運用スキルを、汎用にして公開したもの。スキルの本文とメッセージは日本語。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install guards@shibamasa-plugins
/plugin install workflow@shibamasa-plugins
/plugin install review@shibamasa-plugins
/plugin install testing@shibamasa-plugins
/plugin install devtools@shibamasa-plugins
/plugin install docs@shibamasa-plugins
```

どれも独立していて、必要なものだけ入れられる。

## プラグイン

| プラグイン | 中身 |
|---|---|
| [guards](plugins/guards/README.md) | 作業を止めるフック。破壊的な削除・未検証のマージ・古い main からの push・リポ構造違反の書き込み |
| [workflow](plugins/workflow/README.md) | issue 運用・セッションの引き継ぎ・runbook 記録などのスキルとフック |
| [review](plugins/review/README.md) | PR のレビューを回す。レビュー bot の結果待ち・再レビュー依頼・AI レビューから修正まで |
| [testing](plugins/testing/README.md) | テストを設計して回す。Gherkin のテストケース作成・成果物の検証・全体テストのゲート |
| [devtools](plugins/devtools/README.md) | リポの立ち上げと道具づくり。基本設定の点検・クラウド環境のセットアップ |
| [docs](plugins/docs/README.md) | 画像生成プロンプト・コードで描くモーション動画のスキル |

スキル・フックの一覧と設定は、各プラグインの README にある。

## 前提

- macOS / Linux、`python3`、`git`、`gh`
- `motion-video` は Node.js・Chrome・ffmpeg

## コントリビュート

コミット前の検査フックの入れ方、version の上げ方、リリースの手順は [CONTRIBUTING.md](CONTRIBUTING.md)。脆弱性の報告は [SECURITY.md](SECURITY.md)。

## ライセンス

[MIT](LICENSE)
