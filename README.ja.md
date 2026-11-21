# claude-code-plugins

[English](README.md) | 日本語

[![ci](https://github.com/shibamasa-dev/claude-code-plugins/actions/workflows/ci.yml/badge.svg)](https://github.com/shibamasa-dev/claude-code-plugins/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Claude Code 用のプラグインマーケットプレイス。日々の開発で使っているガード・運用スキルを、汎用にして公開したもの。

> [!IMPORTANT]
> プラグインは手元のマシンでフックやスクリプトを動かす。入れる前に、そのプラグインの README（と `hooks/`）を読む。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install guards@shibamasa-plugins
/plugin install workflow@shibamasa-plugins
/plugin install testing@shibamasa-plugins
/plugin install repo-setup@shibamasa-plugins
/plugin install creative@shibamasa-plugins
/plugin install diagram@shibamasa-plugins
/plugin install lint@shibamasa-plugins
/plugin install inventory@shibamasa-plugins
/plugin install instructions@shibamasa-plugins
/plugin install research@shibamasa-plugins
```

どれも独立していて、必要なものだけ入れられる。

## プラグイン

| プラグイン | 中身 |
|---|---|
| [guards](plugins/guards/README.ja.md) | 作業を止めるフック。破壊的な削除・未マージ worktree の削除・古い既定ブランチからの push。リポ構成のルール（ルールファイルを置いたときだけ）。マージの後のローカルのマージ先ブランチの追従。`--json` なしの `gh issue view --comments`（gh-comments-guard）と `pip freeze`（pip-freeze-guard）も止める。`publish_patterns` を設定すると、`gh` コマンドと GitHub コネクタ経由で公開リポへ出す issue / PR の文面が、自分で登録した非公開値のパターンに当たらないかも調べる（publish-guard。見えない範囲は guards の README に書いてある） |
| [workflow](plugins/workflow/README.ja.md) | 依頼からマージまでの開発フロー（PR のレビューの振り分けと待ち方を含む）・issue 運用・セッションの引き継ぎ・runbook 記録などのスキルとフック、使用枠をファイルへ書き出す mod |
| [testing](plugins/testing/README.ja.md) | テストを設計して回す。Gherkin のテストケース作成・成果物の検証・全体テストのゲート |
| [repo-setup](plugins/repo-setup/README.ja.md) | リポの立ち上げ。基本設定の点検・クラウド環境のセットアップ・プロジェクト専用の実アプリ検証スキルの作成（`verification-skill-builder`） |
| [creative](plugins/creative/README.ja.md) | 画像生成プロンプトと、コードで描くモーション動画のスキル |
| [diagram](plugins/diagram/README.ja.md) | 図をコードで描くスキル。`one-page-diagram` は全体像や概念の一枚図を SVG で描き、要素の種別が混ざらないようにする。`typed-diagram` はフロー図・シーケンス図・状態遷移図・ER 図・C4 を Mermaid で描く。どちらも、描いた図を表示して確かめてから渡す。確かめられなかったときはそう伝える |
| [lint](plugins/lint/README.ja.md) | スキルを作るための道具群。skill-planner（作る前の計画）と skill-lint（スキルに作った人・会社・マシンの固有情報が混ざっていないかを調べ、配布してよいかを報告する）。DESIGN.md を編集したら lint するフックも |
| [inventory](plugins/inventory/README.ja.md) | 手持ちの物の在庫DB。Claude が写真から登録し、読めなかった項目は `needs_review` に残し、NFKC 正規化した検索で引ける。既定は SQLite、Postgres / Supabase にも直結かコネクタ経由で置ける |
| [instructions](plugins/instructions/README.ja.md) | 同梱した指示ファイルを `~/.claude/CLAUDE.md` と同じ扱いで読み込ませる mod。同じ作業ルールがどのマシンでも効く。今は返答の言語とファイルのリンクの 1 ファイルだけ。managed settings や Team / Enterprise のプランで Claude Code の組み込みガードが入る環境では効かない |
| [research](plugins/research/README.ja.md) | X や Web を読むスキル群。今は `research-x` だけ。選んだ X アカウントについて xAI の X 検索に問い合わせ、はっきりしたアップデート告知だけを、指定した言語と口調で要約し、1 件ずつ Slack に流す。状態はチャンネルの履歴だけで持つ |

スキル・フックの一覧と設定は、各プラグインの README にある。

### 旧名からの移行（2026-10）

review は workflow に入り、devtools は repo-setup に、docs は creative に名前が変わった。前の名前で入れていたら入れ直す:

```text
/plugin uninstall review@shibamasa-plugins
/plugin uninstall devtools@shibamasa-plugins
/plugin uninstall docs@shibamasa-plugins
/plugin marketplace update shibamasa-plugins
/plugin install workflow@shibamasa-plugins
/plugin install repo-setup@shibamasa-plugins
/plugin install creative@shibamasa-plugins
```

review の設定（`review_heavy`・`review_light`・`review_auto`・`rereview_threshold`）は workflow の同じキーに入れ直す。

## 言語

英語を基本にし、各プラグインを日本語から英訳している途中。プラグインの CHANGELOG に「メッセージとスキル本文を英語にした」版が載るまでは、そのプラグインのメッセージとスキル本文は日本語のまま。どちらでも Claude は話しかけた言語で返し、スキルの description には日本語の発動フレーズも入れてある。日本語の README は各 `README.md` の隣の `README.ja.md`。

## 前提

- macOS / Linux、`python3`、`git`、`gh`
- `motion-video` は Node.js・Chrome・ffmpeg
- `inventory` は `uv`（MCP サーバーの起動に使う）
- `research` は xAI の API キーと Slack の bot token

## コントリビュート

コミット前の検査フックの入れ方、version の上げ方、リリースの手順は [CONTRIBUTING.md](CONTRIBUTING.md)。脆弱性の報告は [SECURITY.md](SECURITY.md)。

## ライセンス

[MIT](LICENSE)
