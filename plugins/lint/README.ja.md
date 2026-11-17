# lint

[English](README.md) | 日本語

スキルを作るための道具群。`skill-planner` が作る前に計画し、`skill-lint` が作った後に検査する。流れは計画（`skill-planner`）→ 作成（`skill-creator`）→ 検査（`skill-lint`）。

## 導入

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install lint@shibamasa-plugins
```

## スキル

| スキル | 使いどころ |
|---|---|
| `skill-planner` | スキルを作る前の計画。そもそもスキルにすべきかを判断し、必要最小の実装レベル（指示のみ → references → scripts → CLI → ローカル／リモート永続化）を選び、references・scripts・状態の置き場・検証を計画して `skill-creator` に引き継ぐ。状態はスキルのディレクトリ内ではなく `${CLAUDE_PLUGIN_DATA}` に置く計画にする。「スキルにすべき？」「スキルの計画を立てて」で使う |
| `skill-lint` | スキルを不特定多数に配布してよいかを調べる。`/lint:skill-lint <スキルのディレクトリ>` で起動する。観点は「別の会社の人が、別のマシンにこのスキルを入れたら成り立つか。入れた人に何がバレるか」。決定論の `lint.py`（汎用の正規表現だけ）で、メールアドレス、ホームの絶対パスや個人ディレクトリらしいパス、tailnet のホスト、私的な issue 番号、決定の経緯、スキル配下の実行時データを拾う。人名・社名・取引先・私的ボットや私的リポへの依存・環境前提の手順は、エージェントの reviewer が実行環境から集めたヒント（`whoami`・git の user.name / email・gh のログイン名・ホスト名）と lint の結果をもとに判定する。reviewer の指摘は quote が行に逐語で含まれるものだけ残し、カテゴリ別に直し方つきで報告する。直すかどうかは聞いてから |

## フック

| フック | いつ | 何をするか |
|---|---|---|
| skill-creator-chain | Skill の後 | 呼ばれたのが skill-creator（名前空間付きも含む）なら、「スキルの作成・更新が終わったら、そのスキルのディレクトリに skill-lint を走らせる。プロジェクトスコープ（リポ内の `.claude/skills`）は対象外」を伝える。ほかのスキルでは何もしない |

## 固有名の扱い

名前の一覧（denylist）は持たない。名前を集めたファイルを作ると、それ自体が漏れの元になり、手入れも要るため。固有名は reviewer がその場で実行環境から集めたヒントと文脈で判定する。

## 前提

- `python3`（標準ライブラリだけ）
- 任意: `gh`（reviewer が gh のログイン名をヒントにする）、`gitleaks`（secret の検査を任せる。無ければ `skipped` と出る）
- eval グループ B（`scripts/run_reviewer_eval.py`）は `claude` CLI。eval のスクリプトはメンテナ用で、公開していない手元の `evals/` の eval セットを読む
