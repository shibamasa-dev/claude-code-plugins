#!/bin/bash
# The Edge Function's router (router.mjs) under node with a stub database: routing, auth header and error mapping.
set -u
. "$(dirname "$0")/lib.sh"

out=$(node --input-type=module - "$PLUGIN/bridge/functions/agent-bridge/router.mjs" 2>/dev/null <<'JS'
const { handle } = await import(process.argv[2]);
const calls = [];
const db = {
  async status(agent) { calls.push(["status", agent]); return { agent, unread: 2, latest_id: 9 }; },
  async api(token, action, args) {
    calls.push(["api", token, action, args]);
    if (action === "send" && args.thread === "full") throw new Error("hop_limit: thread full already has 20 messages");
    if (token !== "good") throw new Error("unauthorized: the token does not match any participant");
    if (action === "boom") throw new Error("connection reset by peer");
    return { ok: true };
  },
};
const U = "https://x.supabase.co/functions/v1/agent-bridge";
const post = (body, token = "good") =>
  new Request(U, { method: "POST", headers: token ? { Authorization: "Bearer " + token } : {}, body });
const show = async (name, req) => {
  const r = await handle(req, db);
  const j = await r.json();
  console.log(name, r.status, j.error || "-");
};
await show("status", new Request(U + "?agent=claude"));
await show("status_bad_agent", new Request(U + "?agent=Bad%20Id"));
await show("no_token", post('{"action":"inbox"}', ""));
await show("not_json", post("{"));
await show("no_action", post('{"to":"a"}'));
await show("ok", post('{"action":"inbox","limit":5}'));
await show("bad_token", post('{"action":"inbox"}', "nope"));
await show("hop_limit", post('{"action":"send","thread":"full"}'));
await show("internal", post('{"action":"boom"}'));
await show("put", new Request(U, { method: "PUT" }));
const api = calls.find((c) => c[0] === "api" && c[2] === "inbox" && c[1] === "good");
console.log("args_passed", JSON.stringify(api[3]) === '{"limit":5}' ? "yes" : "no");
JS
)
st() { awk -v n="$1" '$1 == n {print $2 "_" $3}' <<<"$out"; }
row 'GET ?agent= answers the status with 200' "$(yesno [ "$(st status)" = 200_- ])" yes
row 'an agent id outside ^[a-z0-9_-]{1,40}$ is a 400' "$(yesno [ "$(st status_bad_agent)" = 400_bad_request ])" yes
row 'a POST without a bearer token is a 401 before the database is asked' "$(yesno [ "$(st no_token)" = 401_unauthorized ])" yes
row 'a body that is not JSON is a 400' "$(yesno [ "$(st not_json)" = 400_bad_request ])" yes
row 'a body without an action is a 400' "$(yesno [ "$(st no_action)" = 400_bad_request ])" yes
row 'a valid call reaches the database and answers 200' "$(yesno [ "$(st ok)" = 200_- ])" yes
row 'the action arguments reach the database without the action key' "$(awk '$1 == "args_passed" {print $2}' <<<"$out")" yes
row 'an unauthorized error from SQL becomes a 401' "$(yesno [ "$(st bad_token)" = 401_unauthorized ])" yes
row 'a hop_limit error from SQL becomes a 409' "$(yesno [ "$(st hop_limit)" = 409_hop_limit ])" yes
row 'an unexpected error becomes a 500 without its text' "$(yesno [ "$(st internal)" = 500_internal ])" yes
row 'other methods are a 405' "$(yesno [ "$(st put)" = 405_bad_request ])" yes
