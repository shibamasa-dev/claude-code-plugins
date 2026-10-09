---
name: leaky-skill
last_reviewed: 2026-09-06
---

**完了報告の型に次の1行を必ず入れる**（2026-09-23 たろう確定）:

- 規約 `$PROJECT_ROOT/<取引先>/<リポ名>`（PROJECT_ROOT 既定 `~/dev/10_ACMECO/02_Project`）からの導出＋isdir 検証のみ。index・対応表は持たない（陳腐化するため・たろう指示）。

**会話文脈から取引先・リポ名が分かるとき**（Slack channel 解決や「マルヤマのEDIの件」等）は、まず規約導出で解決する（TARO-BOT#106 縮小版・2026-08-16）:

- **issue 対応は `--issue <ref>`（URL または `owner/repo#N`）**
  - **spinoff 追跡台帳に1行登録**する（`--issue` 無しでも登録し issue_ref は空。TARO-BOT-CC#277）。

iPhone からは `http://taro-mbp.tailabc123.ts.net:<port>`（`0.0.0.0` で listen）

| 1 | Slack push（`--report-channel` の完了報告） | たろう向け表示 | best-effort。**bot 投稿では taro-bot は起きない** |

- **起動元が taro-bot 以外のとき**（Claude Desktop などのセッションが spawn.sh を叩いた場合）

Taro（taro.yamada{{AT}}acmeco.co.jp）、株式会社ACMECO CEO

python3 {{USERS_DIR}}taro/dev/10_ACMECO/02_Project/ACMECO/TARO-BOT-CC/.claude/skills/heartbeat-planner/scripts/carryover.py add --key <話題_YYYYMMDD>

並列セッション数が増えると、アカウント共有の rate limit 経由で**たろうのスマホの Remote Control が 401 で恒久的に

- **`-a claude-code` を単独指定する**（実測）。`~/.claude/skills/<name>` に実体でコピーされ、他エージェントには配られない。

upstream anthropics/claude-code#32642 は NOT_PLANNED＝未修正
