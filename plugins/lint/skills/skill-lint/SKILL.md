---
name: skill-lint
description: スキル（SKILL.md と scripts/・references/ などの付属ファイル）に、作った人・会社・マシンの固有情報が混ざっていないかを調べ、不特定多数に配布してよいかを報告する。人名・社名・取引先名、ホームの絶対パスや個人ディレクトリを既定値にした記述、社内ホスト、私的な issue 番号、決定の経緯、私的ボット・私的リポへの依存、スキル配下の実行時データを拾う。ユーザーが /lint:skill-lint を打ったとき、または skill-creator 使用後の注入指示があったときだけ使う。それ以外では自分の判断で起動しない。
argument-hint: <スキルのディレクトリ>
---

# skill-lint — スキルを配布してよいかを調べる

観点は「別の会社の人が、別のマシンにこのスキルを入れたら成り立つか。入れた人に何がバレるか」。2 層で調べる。

1. **lint.py（決定論）**: 汎用の正規表現だけで機械的に拾う（メールアドレス・ホームのパス・tailnet・issue 番号・決定の経緯・実行時データ・secret）。安い前処理
2. **reviewer（エージェント）**: 実行環境から固有名のヒントを自分で集め、lint の結果もヒントにして、人名・社名・取引先・私的ボットや私的リポへの依存・環境前提の手順を判定する。固有名と意味の判定はこちらが主役

## 不変条件

1. **勝手に直さない。** 報告して、直すかどうかをユーザーに聞く。
2. **固有名の一覧をどこにも作らない。** 名前を集めたファイル（denylist）を持たない。reviewer がその場で集めて判定する。
3. **reviewer の指摘は validate_findings.py を通ったものだけ報告する。** quote がその行に逐語で無い指摘は捨てる。

## 手順

対象は `$ARGUMENTS`（スキルのディレクトリ）。無ければユーザーに聞く。作業ファイルはセッションの一時ディレクトリ（無ければ `mktemp -d`）に置く。以下の `<tmp>` はその場所。

### ① lint.py を流す

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/skill-lint/scripts/lint.py" "$ARGUMENTS" --json > <tmp>/lint.json
```

| カテゴリ | 深刻度 | 拾うもの |
|---|---|---|
| identity | error | メールアドレス（固有名は調べない。reviewer が判定する） |
| path | error | ホーム配下の絶対パス（macOS・Linux・Windows） |
| path | warn | 標準パス（`~/.claude/`・`~/.config/`・`~/.local/`・`~/.cache/`）以外のホーム起点のパス。ホーム直下の道具の置き場（隠しディレクトリや OS の標準フォルダ）も当たるので、個人のディレクトリ構成かどうかは reviewer が判定する |
| network | error | tailnet のホスト名 |
| secret | error | gitleaks が検出した secret、または gitleaks の失敗（レポートが読めないときも含む） |
| structure | error | スキル配下の `logs/`・`.trash/`・`*.db`・`*.sqlite`・`*.jsonl`・`*.log` などの実行時データ |
| tracker | warn | `owner/repo#N`・`repo#N`・裸の `#N` |
| provenance | warn | 同じ行に日付と「確定・承認・指示・判断・確認」 |

- frontmatter の `last_reviewed` / `review_after` は調べない。行内に `skill-lint: ignore` がある行も調べない。
- 除外は対象スキルの `.skill-lint-ignore` に書いたパスだけ（既定は全ファイルを調べる。実データ由来のフィクスチャが一番漏れやすいので、意図的に漏れを含むテストデータ以外は除外しない）。除外したファイル数を出す。
- プラグインの manifest（`.claude-plugin/plugin.json`・`marketplace.json`）の公開者情報（`name`・`author`・`owner`・`homepage`・`repository` の行）は、公開が前提なのでメールアドレスだけ調べない（パス・ホストは調べる）。
- 読めないファイルは `unreadable`（error）として出す。黙って飛ばさない。
- `gitleaks` が PATH にあれば secret の検査を任せる。無ければ「未実施」と出る。
- 終了コードは error があれば 1、warn だけなら 0。

### ② reviewer を起動する

`Agent(subagent_type: general-purpose)` を 1 つ起動する。prompt は次をこの順で連結する:

1. `${CLAUDE_PLUGIN_ROOT}/skills/skill-lint/references/reviewer-prompt.md` の全文
2. 対象ディレクトリの絶対パスと「全ファイルを Read で読む（lint.py の `excluded_files` は除く）」という指示
3. ヒント: `<tmp>/lint.json` の `findings` から `file`・`line`・`category`・`match` だけを抜いたもの
4. 「JSON 配列だけを出力する」

実行環境から固有名のヒントを集める手順（`whoami`・`git config`・`gh api user`・`hostname`）は reviewer-prompt.md にあり、reviewer が自分で行う。

reviewer の最終出力をそのまま `<tmp>/review.txt` に保存する。

### ③ validate_findings.py で検証する

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/skill-lint/scripts/validate_findings.py" "$ARGUMENTS" <tmp>/review.txt > <tmp>/review.json
```

`valid` だけを報告に使う。`invalid` は件数と理由だけ出す。JSON 配列が取り出せなければ（exit 2）reviewer を 1 回だけ起動し直す。

### ④ 統合レポートを出す

カテゴリごとにまとめ、各指摘に場所（`file:line`）・何が漏れているか・直し方を付ける。同じ行の同じ語を lint と reviewer の両方が拾ったら 1 件にまとめる。冒頭に次を 1 行ずつ出す:

- 判定: error が 0 件で reviewer の high が 0 件なら「配布してよい」、それ以外は「直してから配布する」
- 件数: lint の error / warn、reviewer の有効・無効
- gitleaks の実施状況、除外したファイル数

### ⑤ 直すかを聞く

「直しますか？（全部 / 選んで / 直さない）」と聞いて止まる。直す場合も、置き換え先（役割名・環境変数・プレースホルダ）は指摘ごとに示してから書き換え、終わったら ① からやり直して 0 件を確かめる。

## 付属ファイル

| ファイル | 役目 |
|---|---|
| `scripts/lint.py` | 決定論の検査。`--json` で機械向け、無しで人間向け |
| `scripts/validate_findings.py` | reviewer の出力から JSON 配列を取り出し、quote を行と突き合わせる |
| `references/reviewer-prompt.md` | reviewer への指示（観点・拾うもの・漏れではないもの・出力形式） |
| `scripts/run_evals.py` | eval グループ A（lint.py をフィクスチャに流して採点） |
| `scripts/run_reviewer_eval.py` | eval グループ B（`claude -p` で reviewer を回し、recall と誤検知を数える。`--runs N`） |
