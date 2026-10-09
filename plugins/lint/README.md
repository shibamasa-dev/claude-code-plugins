# lint

スキルなどの成果物を検査する linter 群。今は skill-lint のみ。

```text
/plugin install lint@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `skill-lint` | スキルを不特定多数に配布してよいかを調べる。`/lint:skill-lint <スキルのディレクトリ>` で起動する。観点は「別の会社の人が、別のマシンにこのスキルを入れたら成り立つか。入れた人に何がバレるか」。決定論の `lint.py`（正規表現と denylist）で、人名・社名・メールアドレス、ホームの絶対パスや個人ディレクトリを既定値にした記述、社内ホスト、私的な issue 番号、決定の経緯、スキル配下の実行時データを拾い、その結果をヒントにエージェントの reviewer が正規表現で拾えないもの（取引先名・私的ボットや私的リポへの依存・環境前提の手順）を判定する。reviewer の指摘は quote が行に逐語で含まれるものだけ残し、カテゴリ別に直し方つきで報告する。直すかどうかは聞いてから |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| skill-creator-chain | Skill の後 | 呼ばれたのが skill-creator（名前空間付きも含む）なら、「スキルの作成・更新が終わったら、そのスキルのディレクトリに skill-lint を走らせる。プロジェクトスコープ（リポ内の `.claude/skills`）は対象外」を伝える。ほかのスキルでは何もしない |

## denylist

具体的な名前・ホストはプラグインに入れず、手元の `${XDG_CONFIG_HOME:-~/.config}/skill-lint/denylist.json` に置く。初回はスキルが `build_denylist.py` で作る。

- `auto` 節: 毎回この環境から作り直す（ホームのパスと末尾、ユーザー名、git の user.name / user.email、gh のログイン名と所属 org、ホスト名）
- `manual` 節: 自分の呼び名・社名・社内のボット名やリポ名・社内ホスト名を手で足す。再生成しても残る

プラグインのデータ領域（`${CLAUDE_PLUGIN_DATA}`）に置かないのは、manual 節が利用者の手書きの設定で、プラグインを外しても消えてほしくなく、入れ方（マーケットプレイス）によってデータ領域のパスが変わるため。

## 前提

- `python3`（標準ライブラリだけ）
- 任意: `gh`（denylist に gh のログイン名と org を入れる）、`gitleaks`（secret の検査を任せる。無ければ「未実施」と出る）
- eval グループ B（`scripts/run_reviewer_eval.py`）は `claude` CLI
