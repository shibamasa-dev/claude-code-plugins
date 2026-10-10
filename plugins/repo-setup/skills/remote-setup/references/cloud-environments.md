# クラウド実行環境の仕様メモ(2026-08-15 調査・公式ドキュメント裏取り済み)

出典: https://code.claude.com/docs/en/cloud-environments.md /
https://code.claude.com/docs/en/hooks.md / https://code.claude.com/docs/en/env-vars.md /
https://claude.com/docs/cowork/overview.md

## リモート判定に使える環境変数

| 変数 | 状態 | 用途 |
|------|------|------|
| `CLAUDE_CODE_REMOTE` | **公式**。Anthropic 管理のリモートインフラでのみ `"true"` | **主判定**。ローカルでは絶対にセットされない |
| `CLAUDE_CODE_ENTRYPOINT` | 非公式(env リファレンス未掲載・値が増減しうる) | 副判定(`remote_*` プレフィックス)+リモート内のプラットフォーム分岐(`remote_cowork` / `remote_desktop`)。ローカルは `cli` / `claude-desktop` など複数値 → **「cli 以外=リモート」は誤り** |
| `CLAUDE_CODE_BRIDGE_SESSION_ID` | 公式 | **Remote Control 中のローカルセッション**に付く(リモートではない点に注意。Remote Control は自マシン実行) |
| `CLAUDE_CODE_REMOTE_SESSION_ID` | 公式 | クラウドセッション ID(`cse_` 形式) |
| `CLAUDE_ENV_FILE` | 公式 | ここに `export FOO=bar` を追記するとセッション全体に環境変数を永続化できる |
| `CLAUDE_PROJECT_DIR` | 公式 | リポジトリルート。hook の command 内で使える |

- Cowork にはローカル実行モードもある。`CLAUDE_CODE_REMOTE` 主判定なら「Cowork だがローカル」を誤爆しない。
- 本スキルのゲートはさらに `REMOTE_SETUP_FORCE=1` の明示オーバーライドを許可する
  (Codex / Cursor アダプタとテスト用。それ以外でゲートを緩和・削除しない)。

## セットアップの公式2層機構(claude.ai/code)

| 層 | 定義場所 | 実行 | 権限 |
|----|---------|------|------|
| Setup script(環境層) | claude.ai/code の環境ダイアログ | 新規セッション開始時・Claude Code 起動前・キャッシュ無し時のみ | **root** |
| SessionStart hook(セッション層) | リポ内 `.claude/settings.json` | 毎セッション(matcher: `startup|resume` 等) | 通常ユーザー |

**層の役割分担(公式明記)**: Setup script は「VM 自体のプロビジョニング」
(プリインストールに無いツールチェーン・CLI)。リポジトリのプロジェクトセットアップ
(`npm install` 等)は SessionStart hook に置く。

### Setup script の制約(公式)

- **自己完結で書く**: リポジトリはまだ無い前提(1行でリポ内スクリプトを参照する方式は不可)。
  リポ非依存の固定パス(apt / グローバル CLI / system pip)へインストールする
- **約5分以内**(超えると環境キャッシュが作れない。独立インストールは `&` + `wait` で並列化)
- **exit 0 必須**(非0だとセッションが起動失敗。重要でないステップは `|| true`)
- ネットワークは環境の設定に従う(既定 Trusted はい主要レジストリ許可)

### 環境キャッシュ(公式)

- Setup script 完了後にファイルシステムを**スナップショット**し、以後のセッションはそこから開始
  (Setup script はスキップ)。**キャッシュは環境単位でリポ非依存**
- 残るのは**ファイルだけ**(起動したプロセス・DB・docker compose スタックは残らない → 毎セッション hook で起動)
- 再構築条件: Setup script かネットワーク許可の変更時、または**約7日**の期限切れ。セッションの resume では再実行されない

### SessionStart hook の仕様

- クラウドセッションが読むのは**リポ内 settings.json と org managed settings のみ**
  (ユーザーレベル `~/.claude/settings.json` は読まれない)
- stdout はエージェントの context に注入される → 出力は1〜3行に保つ
- stdout が `{` で始まると JSON 解釈される(`{"async": true, "asyncTimeout": 300000}` で非同期化可。
  初回は同期で作り、遅ければ非同期化を検討)
- hook のタイムアウトは既定 60 秒(本スキルは hook 定義に `timeout: 120` を設定)
- 失敗してもセッションを止めない設計にする(常に exit 0 + WARNING 出力)

## VM スペック・制約(Anthropic ホスト)

- Ubuntu 24.04 LTS (x86_64) / 約4 vCPU / 16GB RAM / 30GB disk。リソース超過で VM がタスク停止
- プリインストール: Python 3(pip, poetry, uv, pytest, ruff...) / Node 20-22(npm, yarn, pnpm...) /
  Ruby / PHP / Java / Go / Rust / Docker / PostgreSQL 16 / Redis 7 / git, jq, yq, ripgrep, tmux
- **system pip は PEP 668(externally-managed)** → root の Setup script では
  `pip install --break-system-packages` を使う。セッション層の venv からは
  `python3 -m venv --system-site-packages` で system のパッケージが見える
- GUI 無し → ビューア系(ocp-vscode 等)は使えない。CAD はヘッドレス検証(export + 数値検証)
- devcontainer はクラウドセッション非対応
- ネットワーク: None / **Trusted(既定: npm, PyPI, RubyGems, crates.io 等 + GitHub)** / Custom / Full。
  GitHub アクセスはプロキシ経由で、セッションに紐づかないリポの release asset 取得は 403
- 環境変数・Setup script は環境を使う全員に可視 = **secrets を置かない**(専用 secrets store は未提供)

## 他プラットフォームのアダプタ(将来対応)

どちらもセットアップ機構自体がクラウド専用なので、`REMOTE_SETUP_FORCE=1` を付けて
セッション層コア(setup.sh)を呼ぶ薄いアダプタでよい。環境層の内容は各機構に統合する。

### OpenAI Codex(クラウド)

- 環境設定の `setup` スクリプトがエージェント起動前に実行(コンテナ状態は約12時間キャッシュ)
- アダプタ: setup スクリプトに environment-setup.sh の内容を統合し、末尾に
  `REMOTE_SETUP_FORCE=1 bash scripts/remote-setup/setup.sh` を追加
- 環境変数の永続化は `~/.bashrc`、lint/test コマンドの伝達は `AGENTS.md`
- Docs: https://developers.openai.com/codex/cloud/environments

### Cursor(Cloud Agents)

- リポにコミットする `.cursor/environment.json` の `install`(冪等必須)/ `start` / `terminals`
- アダプタ: `"install": "REMOTE_SETUP_FORCE=1 bash scripts/remote-setup/setup.sh"` を基本に、
  環境層も install に統合(キャッシュされる)。シークレットは Cursor 側の管理機構
- Docs: https://cursor.com/docs/cloud-agent/setup

## 未実測(2026-08-15 時点)

- クラウド Cowork での SessionStart hook 実行・`CLAUDE_CODE_REMOTE` の実値は初回適用リポで実測確認する
  (リモートセッションで `[remote-setup]` 行と `~/.cache/remote-setup/*.log` を見る)
