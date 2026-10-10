# Changelog

review プラグインの変更履歴。書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/)、版は plugin.json の `version`。

## [0.4.2] - 2026-10-10

### Removed
- dev-flow・pr-review-triage：自動マージの判定で guards の設定 `merge_allowed_repos` も読む移行中の扱いを消した。`.claude/dev-flow.json` だけを見る

## [0.4.1] - 2026-10-10

### Changed
- pr-review-triage：本文の実例から案件の中身を外し、eval の出典をリポ名ではなく「このリポジトリ（公開リポ）」と書いた

## [0.4.0] - 2026-10-09

### Added
- `pr-review-triage` スキル：PR を作った直後・push の後に、手元の `git diff --numstat` を `scripts/classify.sh` で light / heavy に振り分ける。light は Claude が組み込みの `code-review` でレビューして PR 本文の `## レビュー（Claude）` に書き、CI だけ待つ。heavy はレビューツールにコネクタ（`add_issue_comment`・`request_copilot_review`）で頼み、待って評価・対応する。再レビューを頼むかの判断と依頼もここで持つ
- ツールごとの中身を `references/tools/<id>.md`（`codex`・`coderabbit`・`copilot`・`gemini`・`cursor-bugbot`）に 1 ツール 1 ファイルで置いた
- userConfig `review_tools`（`review-bots:` 行が無いときに使うツール）と `rereview_threshold`（再レビューを頼む重い指摘の件数。既定 3）

### Changed
- 使うツールは `review-bots:` 行 → userConfig `review_tools` の順に決め、どちらも無ければユーザーに聞く。過去の PR に来た bot からの推測はやめた（`detect-bots.sh` は行も設定も無ければ exit 4）
- `review-bots:` 行の Cursor Bugbot の id は `cursor` から `cursor-bugbot` に変えた
- dev-flow-gate：PR を作った後の案内と、待ちを始めずに終えるときのメッセージの案内先を `pr-review-triage` にした
- dev-flow：5・6 段の手順の参照先を `pr-review-triage` にした

### Removed
- `pr-review-wait`・`pr-rereview` スキル（`pr-review-triage` に統合。別名は残さない）、`references/bots.md`、`scripts/post_rereview.sh`（`gh` で投稿していた）

## [0.3.1] - 2026-10-06

### Changed
- dev-flow：ユーザーに決めてもらうこと（issue 化、アーキレビューの GO、マージの提案など）は、文章に埋めずに選択肢として出すようにした。Claude Code の `AskUserQuestion` やプロジェクトのスレッドの選択カードなど、セッションに選択肢を出すツールがあればそれを使い、無ければ文章で選択肢を並べる
- dev-flow：マージの提案に PR へのリンク、レビューツールごとの状況、CI の結果、`## 結果` を書いた issue（口頭の依頼なら PR 本文）を載せるようにした。自動マージのリポでは提案を出さずにマージへ進む。構造変更の GO 待ちの間は、推奨の選択肢でも実装を始めない
- dev-flow：自動マージのリポでも、client / product のリポの PR はユーザーに回す（pr-review-wait の例外の範囲とそろえた）

## [0.3.0] - 2026-10-06

### Added
- `dev-flow-gate` フック：PR 本文の `Closes` / `Refs` と `Arch-Review:` の欄が無い PR 作成、待ちを始めずに終えるターン（PR ごとに1回）、`Closes` 先の `## 結果` の記録が無いマージを止める。GitHub コネクタと `gh` の両方を見る

### Changed
- `pr-review-wait`・`pr-rereview`：自動マージのリポを、guards の設定 `merge_allowed_repos` からリポの `.claude/dev-flow.json` に切り替えた（移行中は `merge_allowed_repos` のリポも同じ扱い）

## [0.2.0] - 2026-10-06

### Added
- `dev-flow` スキル：issue の対応も口頭の依頼も、依頼からマージまでを1本のフローで回す入口。構造変更の基準とアーキレビュー、Issue Fields（`Arch Review`・`Verification`）が無いときの警告、実装後の自己レビュー、PR 本文の `Closes` / `Refs` と `Arch-Review:` の欄、マージ前の `## 結果`、リポ単位の自動マージ（`.claude/dev-flow.json`）を持つ

## [0.1.0] - 2026-10-06

### Added
- workflow プラグインから `pr-review-wait`・`pr-rereview` とコマンド `review-and-fix` を移した（中身は変えていない）。コマンドは `/review:dev-process:review-and-fix` になる
