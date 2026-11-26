# print

[English](README.md) | 日本語

手元のファイル（PDF・画像・テキスト・HTML・Markdown）を、macOS / Linux の CUPS（`lp`）で印刷するスキル。既定は白黒・両面長辺とじ・A4 の普通紙・1 面 1 ページで、ページ番号つき。送る前に、ページ数・紙の枚数・設定・プリンタを示す。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install print@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `print` | 「印刷して」「両面で印刷」「カラーで」「2 ページずつ割り付けて」。Claude が印刷するのは頼まれたときだけ。まず dry-run を走らせ、何をどのプリンタに紙何枚で送るかを 1〜2 行で示してから送る。実体は `skills/print/scripts/print.py`（Python・標準ライブラリだけ）と `skills/print/scripts/to_pdf.sh` |

## print の動き

1. **ファイルを用意する。** PDF はそのまま、画像は 1 ページとして送る。HTML・Markdown・テキストはヘッドレス Chrome で PDF にし、ページ下中央に「ページ / 総ページ」を入れる（Markdown は pandoc があればそれで、無ければ CDN から読んだ marked で描く）。ページ番号の無い PDF には、印刷前に qpdf で番号を重ねる。qpdf が無いときや、ページの大きさがそろっていないときは番号なしで印刷し、理由を出す。
2. **オプションを選ぶ。** `lp` が受け付ける `-o` のキーと値はプリンタ（ドライバ）ごとに違うので、`print.py` はそのプリンタの `lpoptions -p <プリンタ> -l` を読んで選ぶ。PPD 系のキー（`ColorModel`・`Duplex`・`PageSize`・`MediaType`）と IPP 系のキー（`print-color-mode`・`sides`・`media`・`media-type`）のどちらにも対応する。CUPS は知らないオプションを黙って無視するので、一覧に無い設定は送らずに「Could not set」として報告する。
3. **数えて示す。** ページ数は `pdfinfo` で数え、紙の枚数は `ceil(ceil(ページ数 / 1 面のページ数) / 両面なら 2) × 部数` で出す。設定と、そのまま実行する `lp` のコマンドも出す。`--dry-run` はここで止まる。
4. **送る。** `lp` を実行し、ジョブ ID とキュー（`lpstat -o`）、取り消し用の `cancel <ジョブ ID>` を出す。

オプション: `--printer`・`--color`・`--simplex`・`--short-edge`・`--size`・`--copies`・`--2up`・`--no-number`・`--dry-run`。

## 設定

設定項目は無い。プリンタは指定が無ければ `lpstat -d` のシステム既定で、プラグインはプリンタ名を保存しない。Chrome / Chromium が標準の場所に無ければ、環境変数 `CHROME` にパスを入れる。

### ファイルの置き場所

変換した PDF と番号を付けた PDF は、システムの一時ディレクトリの下に新しく作るディレクトリ（`print-skill.*`）に置く。実行後も消さない。プラグインのデータには何も残さないので、アンインストールで消えるものはほかに無い。

## 制限

- IPP 系のキーと `KGray` の値は、作り物の `lpoptions` 出力でしか確かめていない。実機で確かめたのは、macOS ドライバの EPSON インクジェット 1 台だけ。
- PDF に元からページ番号があるかは、先頭・2 ページ目・最終ページの上下のテキストから推定している。珍しい書式（例: 「— 3 —」）は番号なしと判定され、番号が二重に付くことがある。そのときは `--no-number` を付ける。
- pandoc が無い環境の Markdown は marked を読むのにネットワークが要る。オフラインなら整形済みテキストのまま印刷する。

## 前提

- CUPS（`lp`・`lpstat`・`lpoptions`）のある macOS / Linux
- poppler（`pdfinfo`・`pdftotext`）: `brew install poppler` / `apt install poppler-utils`
- HTML・Markdown・テキストを印刷するなら Google Chrome か Chromium
- 任意: qpdf（既存の PDF へのページ番号）、pandoc（Markdown）
- Python 3.9 以上（標準ライブラリだけ）

## テスト

```bash
bash plugins/print/tests/run-all.sh
```

オフラインで紙も使わない。どのケースも保存した `lpoptions -l` の出力に対して `print.py --dry-run` を走らせ、`PATH` の先頭に置いた `lp`・`lpstat`・`lpoptions`・`cancel` の代役が呼び出しを記録する。最後の行で呼び出しが 0 件だったことを確かめる。qpdf や Chrome が要るケースは、それが無い環境では飛ばし、確かめた数には入れない。
