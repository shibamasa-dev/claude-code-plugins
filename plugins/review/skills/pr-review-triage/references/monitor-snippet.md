# PR レビュー待機の Monitor スニペット

`pr-review-triage` skill の heavy の「待つ」をローカルで行うときの実体（クラウドは PR イベントの購読で待つので使わない）。
`persistent: true` で起動し、TaskStop で明示停止するまで動く。Monitor の `allowed_domains` に `api.github.com` を入れる。

```bash
# ⚠️ このループは起動時刻より後しか拾わない。立てる前に既存の未解決スレッドを必ず1回さらうこと
#    （PR 作成の数分後には初回レビューが着くため、Monitor だけでは取りこぼす）。
#    bot 以外(自分の返信)を除外しないと通知が溢れて本物のレビューが埋もれる。
# ⚠️ Monitor は sandbox 内で走り、gh は sandbox 内で TLS 検証に失敗する（x509: OSStatus -26276）。
#    gh api は使わず curl + gh auth token で取る。
# ⚠️ 取得結果は printf '%s' で jq に渡す。Bash ツールは zsh で、zsh の echo は JSON 文字列中の \n を
#    本物の改行に展開して jq を落とす（stderr に出るだけで通知は0件になる）。
# 取得失敗・パース失敗は FETCH_FAILED / PARSE_FAILED として通知に出す（「0件」と区別するため）。
TOKEN=$(gh auth token 2>/dev/null); [ -z "$TOKEN" ] && echo "FETCH_FAILED no_token"
API=https://api.github.com/repos/{owner}/{repo}
last=$(date -u +%Y-%m-%dT%H:%M:%SZ)
# 待つ bot の投稿者（scripts/detect-bots.sh --regex の出力。Monitor の前に一度だけ取って埋め込む）
BOTS='{bots_regex}'
# CodeRabbit の自動サマリ（walkthrough）は push のたびに更新されるので本文は通知しない。
# ただし指摘ゼロのとき CodeRabbit は review を作らず、完了をこの walkthrough の中に書くだけなので、
# 「No actionable comments」と、未レビューの合図（rate limited・plan limit）だけは状態行として出す
# （前者を出さないと完了を検知できない。後者は「終わり」ではなく待ち直しの合図）。
# 未レビューの合図は summarize とは別のコメントで来ることもあるので、$NOISE に当たらなくても状態行に回す。
NOISE='auto-generated comment: summarize|review in progress'
get() { curl -sf -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.github+json" "$1"; }
while true; do
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  for pr in {pr_numbers}; do
    # reviews は since 未対応（黙って無視され全件返る）ため jq 側で絞る
    r=$(get "$API/pulls/$pr/reviews?per_page=100") || { echo "FETCH_FAILED PR#$pr reviews"; r='[]'; }
    printf '%s' "$r" | jq -r --arg l "$last" --arg b "$BOTS" --arg p "$pr" \
      '.[] | select(.submitted_at > $l) | select(.user.login | test($b; "i")) | "[PR#\($p) review] \(.user.login): \(.state) \(.body[0:200] | gsub("\n";" "))"' \
      || echo "PARSE_FAILED PR#$pr reviews"
    c=$(get "$API/pulls/$pr/comments?since=$last&per_page=100") || { echo "FETCH_FAILED PR#$pr comments"; c='[]'; }
    printf '%s' "$c" | jq -r --arg b "$BOTS" --arg p "$pr" \
      '.[] | select(.user.login | test($b; "i")) | "[PR#\($p) comment] \(.user.login) \(.path | split("/") | last):\(.line // .original_line) \(.body[0:250] | gsub("\n";" "))"' \
      || echo "PARSE_FAILED PR#$pr comments"
    i=$(get "$API/issues/$pr/comments?since=$last&per_page=100") || { echo "FETCH_FAILED PR#$pr issue_comments"; i='[]'; }
    printf '%s' "$i" | jq -r --arg b "$BOTS" --arg n "$NOISE" --arg p "$pr" \
      '.[] | select(.user.login | test($b; "i"))
        | if ((.body | test($n)) or (.body | test("rate limited|plan limit"; "i"))) then
            (if (.body | test("No actionable comments|rate limited|plan limit"; "i")) then "[PR#\($p) coderabbit-status] actionable_none=\(.body | test("No actionable comments")) not_reviewed_limit=\(.body | test("rate limited|plan limit"; "i"))" else empty end)
          else "[PR#\($p) issue-comment] \(.user.login): \(.body[0:250] | gsub("\n";" "))" end' \
      || echo "PARSE_FAILED PR#$pr issue_comments"
    # Codex 等は指摘ゼロのとき reviews に載らず PR へのリアクション（👍）で返す。👀 はレビュー中
    x=$(get "$API/issues/$pr/reactions") || { echo "FETCH_FAILED PR#$pr reactions"; x='[]'; }
    printf '%s' "$x" | jq -r --arg l "$last" --arg b "$BOTS" --arg p "$pr" \
      '.[] | select(.created_at > $l) | select(.user.login | test($b; "i")) | "[PR#\($p) reaction] \(.user.login): \(.content)"' \
      || echo "PARSE_FAILED PR#$pr reactions"
  done
  last=$now
  sleep 30
done
```

起動前のさらい（未解決スレッドの一覧。これを先に潰してから Monitor を立てる）:

```bash
gh api graphql -f query='{ repository(owner:"{owner}", name:"{repo}") { pullRequest(number:{pr}) {
  reviewThreads(first:20) { nodes { isResolved comments(first:1) { nodes { author{login} path body } } } } } } }' \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
```

（さらいは Monitor の外で叩くので `gh` でよい。ただし sandbox 内の Bash では同じ TLS 失敗で落ちるので sandbox 外で実行する。）

注意: Monitor 通知の本文は truncate される。新着検知後は必ず `gh api` で
reviews / comments の**全文を再取得**してから評価する（通知本文だけで判断しない）。

**満了通知が0件でも「まだ来ていない」と読まない。** 一次ソースを引き直してから判断する。
Monitor の出力ファイル（`tasks/<id>.output`）に jq や curl のエラーが残っていないかも見る。
