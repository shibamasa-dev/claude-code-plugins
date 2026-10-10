---
name: remote-setup
description: >-
  リポジトリにリモート実行環境(claude.ai/code のクラウド環境・Cowork のクラウド VM)用の
  セットアップ scaffold を生成・更新する。生成物はローカルでは一切発動しないゲート付き。
  「リモートセットアップを追加/更新して」「クラウド環境でこのリポを使えるように」
  「Cowork / claude.ai/code でこのリポを動かしたい」「リモートセッション開始時に依存を入れたい」
  「CAD など重いツールをクラウドで使いたい」「remote setup」「session-start hook を作って」等で
  必ずこのスキルを使うこと。リモートで必要なツールの導入をリポごとに環境層
  (environment-setup.sh)とセッション層(steps.sh)に振り分けて配線する。
  既存 scaffold へのツール追加・更新、Codex / Cursor クラウドエージェント対応の相談にも使う。
last_reviewed: 2026-09-06
review_after: 2027-03-05
---

# remote-setup — リモート実行環境用セットアップの scaffold 生成

## 設計原則

- 対象: claude.ai/code のクラウド環境、Cowork のクラウド VM。Codex / Cursor の
  クラウドサンドボックスへは `REMOTE_SETUP_FORCE=1` を使う薄いアダプタで拡張する。
- **ローカルでは絶対に発動しない**。生成される setup.sh は冒頭ゲートで
  `CLAUDE_CODE_REMOTE=true`(公式フラグ・主判定)または `CLAUDE_CODE_ENTRYPOINT=remote_*`
  (実測値・副判定)または `REMOTE_SETUP_FORCE=1`(明示オーバーライド)のときだけ動く。
  「`cli` 以外はリモート」という判定は誤り(ローカル Desktop app は `claude-desktop`)。
  このゲートはどんな理由があっても削除・緩和しないこと。
- 公式の2層機構に正確に合わせる(層の役割は公式に明記がある):

| 層 | ファイル | 実行 | 置くもの |
|----|---------|------|---------|
| **環境層** | `environment-setup.sh` → 内容を claude.ai の Setup script 欄に**丸ごと貼る** | 初回のみ・root・スナップショットが約7日キャッシュ | VM プロビジョニング: apt・重量パッケージ・グローバル CLI。**リポはまだ無い前提で自己完結・固定パスへ** |
| **セッション層** | `steps.sh`(setup.sh が駆動) → SessionStart hook | 毎セッション・通常ユーザー | リポの状態に追従する軽い処理: 依存同期・venv・verify |

- クラウドセッションはリポ内 `.claude/settings.json` **しか読まない**(ユーザーレベル設定は
  読まれない)。したがって成果物は必ずリポにコミットする。
- 詳細仕様(環境変数・VM スペック・キャッシュ・アダプタ・出典)は
  `references/cloud-environments.md` を**生成前に必ず読む**こと。

## 手順

### 1. scaffold を生成する

```bash
python3 <このスキルのパス>/scripts/scaffold.py <repo-root>
```

| パス | 扱い |
|------|------|
| `scripts/remote-setup/setup.sh` | セッション層共通ランナー。**毎回テンプレで上書き**(手で編集しない) |
| `scripts/remote-setup/steps.sh` | セッション層のリポ固有手順。**既存なら保持** |
| `scripts/remote-setup/environment-setup.sh` | 環境層(UI に貼る内容)。**既存なら保持** |
| `.claude/settings.json` | SessionStart hook をマージ追記(既存設定は保持・重複追加しない) |

### 2. 2層に振り分けて実装する

リポを分析し(パッケージマニフェスト・lockfile・CLAUDE.md・CI 設定・主要 import)、
必要ツールを振り分ける。判断基準:

| 置き場 | 基準 | 例 |
|--------|------|-----|
| `environment-setup.sh`(環境層) | root が要る / 30秒超 / 変化しないもの | apt、CAD 系重量パッケージ、グローバル CLI |
| `light_steps`(セッション層) | リポの状態に追従すべきもの(冪等・数十秒以内) | `npm ci`、`pip install -e .`、venv 作成 |
| `verify`(セッション層) | 数秒で環境の死活が分かる | `command -v`、import チェック |

迷ったらセッション層(毎回走っても冪等なら害がない)。環境層は約5分の実行制限あり。

実装時の約束:
- **環境層は自己完結**: リポ参照禁止(実行時点でリポが無い)。system pip へは
  `pip install --break-system-packages`(Ubuntu 24.04 は PEP 668)。
- **Python はセッション層でリポ直下 `.venv`**。環境層で system に入れた重量パッケージは
  `python3 -m venv --system-site-packages` で見せる。
- **非対話**: `-y` / `DEBIAN_FRONTEND=noninteractive`。環境層は各ステップ `|| true`(exit 0 必須)。
- 必須環境変数は `REQUIRED_ENV_VARS` に列挙。**値はリポに書かない**(claude.ai の環境
  ダイアログで設定。setup は存在チェックと警告のみ)。secrets はコミット禁止。
- Trusted 既定で足りないネットワークホストは steps.sh 冒頭のコメント欄に列挙。

### 3. ローカル安全確認(必須)

```bash
env -u CLAUDE_CODE_REMOTE -u REMOTE_SETUP_FORCE bash scripts/remote-setup/setup.sh; echo "exit=$?"
```

**無出力・exit 0 であること**。何か出力されたらゲートが壊れている。
`bash -n` で両スクリプトの構文も確認する。
⚠️ `REMOTE_SETUP_FORCE=1` や `CLAUDE_CODE_REMOTE=true` を付けてローカル実行してはいけない
(実インストールがローカルマシンに走る)。ロジック確認は verify 単体まで。

### 4. ユーザーへ報告(このテンプレで)

```
## remote-setup 適用結果
### 生成・変更ファイル
- (一覧)
### claude.ai/code 環境ダイアログでの設定(ユーザー操作)
1. Setup script 欄に scripts/remote-setup/environment-setup.sh の【内容を丸ごと】貼り付け
   (コミットだけでは環境層は動かない。内容を変えたら貼り直し=キャッシュ再構築)
2. Environment variables: (REQUIRED_ENV_VARS の一覧、無ければ「なし」)
3. Network access: (Trusted で足りる / Custom + ホスト一覧)
### 動作確認
リモートセッションを開いて [remote-setup] の行が context に出るか確認。
詳細ログ: cat ~/.cache/remote-setup/<repo名>.log
※ hook はデフォルトブランチにマージされた後のセッションから有効
```

## 更新フロー

- セッション層の変更は steps.sh を編集するだけ。ハッシュが変わると次のリモートセッションの
  hook が自動で light_steps を再適用する。
- 環境層の変更は environment-setup.sh を編集し、**claude.ai の Setup script 欄に貼り直す**
  ことをユーザーに依頼する(貼り直しでキャッシュが再構築される)。
- setup.sh 共通部の改善はこのスキルを更新してから各リポで scaffold.py を再実行して配る。

## Codex / Cursor への将来対応

共通コア(setup.sh)はそのまま、各プラットフォームのクラウド専用セットアップ機構から
`REMOTE_SETUP_FORCE=1 bash scripts/remote-setup/setup.sh` を呼ぶ薄いアダプタを追加する。
具体手順は `references/cloud-environments.md` の「他プラットフォームのアダプタ」参照。
