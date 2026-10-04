# リポジトリ構造ルール（docs/・scripts/・一時ファイル）

> guards プラグインの file-guard フックが、Write の前にこのファイルの `<!-- guard:… -->` ブロックを読んで判定する。docs/ 直下の .md・scripts/ 直下のスクリプトの新規作成を止める。
>
> **これはプラグイン同梱の既定。** `~/.claude/rules/repo-structure.md` を置くとそちらが優先され、環境変数 `FILE_GUARD_SPEC` を設定するとさらにそれが優先される。値を変えるときはブロックを1行直せば、フックの挙動と deny メッセージが同時に変わる。

## docs/ の構造

- **docs/ 直下に .md を置かない。** 例外は `docs/README.md` 1枚のみ（インデックス: 何がどこにあるかを1行ずつ。内容は書かない）。

<!-- guard:docs-allow-filenames -->
- README.md
<!-- /guard:docs-allow-filenames -->
- **サブフォルダは「種類」で切る。** 規定セットから**必要になったものだけ**作る（空フォルダを先に掘らない）:
  - `spec/` — 仕様・設計（何を作るか・どう作るか）【上書き型: 常に現在の正】
  - `adr/` — 意思決定記録（なぜそうしたか）【追記型: `YYYYMMDD_` prefix】
  - `research/` — 調査・検証・実測レポート（何がわかったか）【追記型: `YYYYMMDD_` prefix】
  - `ops/` — 運用手順・runbook（どう動かすか）【上書き型】
  - `reference/` — 外部契約・API・スキーマ（何が正か）【上書き型】
- **迷ったら1問判定**: 下のブロックが規定セットと判定の正典（hook の deny メッセージもここから組み立てる）。

<!-- guard:docs-subfolders -->
- spec: 何を・どう作る
- adr: なぜ
- research: 何がわかった
- ops: どう動かす
- reference: 何が正か
<!-- /guard:docs-subfolders -->
- **サブフォルダに README.md を作らない。** インデックスは `docs/README.md` に集約。サブツリーが深く複雑化して案内が要るなら README でなく **CLAUDE.md を置く**（ディレクトリスコープで agent が自動で読む）。
- **フェーズで切らない。** プロジェクトは「調査→要件→構築→開発→テスト→調査→改善→…」とループするため、`01_research/` 等のフェーズ切りは2周目で破綻する。種類切りはフェーズと直交し、ループの成果物は追記型（research・adr＝履歴として積む）と上書き型（spec・ops・reference＝現在の正へ更新）に落ちる。0→1 は research＋spec 数枚から始まり、1→100 で spec が肥大したらトピック分割（例: `spec/auth/`）し、深くなった所へ CLAUDE.md でナビを置く。
- 規定セットに収まらないトピック大物（例: `accounting/`）は並列に置いてよい。ただし `docs/README.md` に1行登録する。
- **既存リポへの遡及リファクタはしない。** 新規文書から適用。既存文書は触ったついでに移動してよい（リンク切れに注意）。

## docs と実装の境界（二重管理の禁止）

- **実装から機械的に読み取れるものは docs に書かない。** SoT は実装: DB スキーマ＝migration/DDL、型・API シグネチャ＝型定義、設定値・コマンド一覧＝コード/--help、ディレクトリ構成＝ls。docs にはポインタ1行（例: 「スキーマは `migrations/` が正」）まで。コピーを書かなければ陳腐化するものが最初から無い。
- **docs に書くのは実装に現れないものだけ**: why（adr）／要件・意図・スコープ（spec）／コンポーネント跨ぎの流れ・シーケンス（spec）／調査・実測（research）／順序・タイミング・注意が本質の運用（ops）。
- **判定1問**: 「コードを読めば正確に分かるか？」YES → 書かない。

## scripts/ の構造

- **scripts/ 直下にスクリプトを置かない。** 機能・ドメイン単位のサブフォルダで切る（例: `scripts/scheduler/`・`scripts/launcher/`・`scripts/deploy/`）。「スクリプト」と見なす拡張子:

<!-- guard:script-extensions -->
- .sh
- .py
- .js
- .ts
- .mjs
- .rb
- .zsh
- .bash
<!-- /guard:script-extensions -->

- **例外: skill のレイアウト。** skill は `<skill>/scripts/` 直下にスクリプトを置くのが正しい形（`skill-creator` の型）なので、この規約の対象外にする。リポ直下の `scripts/` を機能別サブフォルダへ割る話とは別物。

<!-- guard:exemptions -->
- path-component-skills: パス要素のどこかが `skills` であるツリー全体（skill は `<skill>/scripts/` 直下にスクリプトを置く形が正しいため）
- sibling-skill-md: `scripts/` の親ディレクトリに `SKILL.md` がある場合（skill は `skills/` 配下とは限らないため）
<!-- /guard:exemptions -->

  ブロックから ID を消すとその例外は効かなくなる（hook は ID を読んで有効・無効を決める）。
- エントリポイントと内部ヘルパーが混在してきたら、ヘルパーを `lib/` へ分離するか `_` prefix で区別する。
- 案内が要るなら README でなく CLAUDE.md（docs と同じ方針）。

## 一時ファイル

- 置き場はシステムプロンプトの scratchpad 指示に従う（リポ内に作ってよいのはコミット予定の成果物だけ）。以下はプロンプトに無い補足。
- gitignore 済みパス（`.claude/state/` 等）は**永続 state の置き場**であって一時ファイル置き場ではない。一時物を「gitignore 内だから」とリポに置かない。
- コミット前に `git status` で untracked の残骸ゼロを確認する。
