# コントリビュート

issue と PR は日本語でも英語でもよい。

## コミット前の検査フック

コミット前に、個人環境（ホームの絶対パス・メールアドレス）の混入とコミット作者のメールを検査するフックを同梱している。clone ごとに 1 回（フックを更新したときも）、中身を確認してから入れる:

```bash
bash .githooks/install.sh
```

`origin/main` のフックと検査スクリプトを `.git/hooks/` にコピーして使う（作業ツリーのファイルを直接実行しないので、外部の PR ブランチを checkout してもそのコードは走らない）。`install.sh` 自体は作業ツリーから実行されるので、main を checkout した状態で中身を確認してから実行する。既に別の場所のフック（グローバルの `core.hooksPath` 等）を使っていれば、そこには書き込まず、検査のあとに続けて呼ぶ。

追加で止めたい固有名があれば `~/.config/claude-code-plugins/blocked-patterns` に 1 行 1 正規表現で書く（リポには置かない）。同じ検査は CI（`.github/workflows/`）でも走る。

## PR を出す前に

手元で CI と同じ検査を回す:

```bash
claude plugin validate --strict .
for p in plugins/*/; do claude plugin validate --strict "$p"; done
python3 .github/scripts/check-repo.py
for t in plugins/*/tests/run-all.sh; do bash "$t"; done   # テストは macOS 前提
```

## version と CHANGELOG

- プラグインの中身を変えたら、その plugin.json の `version` を上げる。同じ version のままだと `claude plugin update` が最新と判断して中身を入れ替えない。CI（`check-version-bump.sh`）が、上がっていない PR を落とす。README・CHANGELOG・`tests/` だけの変更は対象外
- version を上げたら、そのプラグインの `CHANGELOG.md` に同じ版の見出し（`## [0.1.3] - 2026-10-06`、日付は PR を出す日）と、利用者から見た変更を足す。見出しが無いと CI が落とす
- version は marketplace.json の各エントリには書かない（plugin.json が優先され、両方に書くと validate が警告する）

## リリース

main にマージして ci が通ると、`release.yml` が version の上がったプラグインに `<plugin>--v<version>`（例: `guards--v0.1.3`）のタグを打つ。中身は `claude plugin tag --push` で、plugin.json と marketplace.json の version の食い違いもそこで止まる。タグの前に leak-scan と同じ社内の固有名の検査もかける。

取りこぼしを手で打つときは、main を最新にして ci が緑なのを確かめてから:

```bash
claude plugin tag plugins/guards --dry-run   # 確認
claude plugin tag plugins/guards --push
```
