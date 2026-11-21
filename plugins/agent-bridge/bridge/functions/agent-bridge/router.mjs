// HTTP router for the agent-bridge Edge Function. Plain JavaScript with no imports, so the tests run it with node.
// It only passes parameters through: every rule lives in SQL (agent_bridge.api and agent_bridge.status).
//
//   GET  <function URL>?agent=<id>          no auth  -> {"agent", "unread", "latest_id"} (counts only, never a body)
//   POST <function URL>  Authorization: Bearer <token>  {"action": "send"|"inbox"|"ack"|"participants"|"message", ...}
//
// db is {status(agent) -> object, api(token, action, args) -> object}; index.ts backs it with Postgres.

const HTTP_STATUS = {
  unauthorized: 401,
  bad_request: 400,
  unknown_agent: 400,
  not_found: 404,
  thread_closed: 409,
  hop_limit: 409,
};
const AGENT_ID = /^[a-z0-9_-]{1,40}$/;
// The request text, in characters. Room for a 20000-character body even if every character arrives \u-escaped
// (6 characters each, 12 for a surrogate pair); SQL enforces the real 20000-character limit on the body.
const MAX_REQUEST_CHARS = 256 * 1024;

function json(status, obj) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });
}

// "hop_limit: thread x already has ..." -> ["hop_limit", "thread x already has ..."]
export function splitError(message) {
  const m = /^([a-z_]+): (.*)$/s.exec(String(message || ""));
  return m && m[1] in HTTP_STATUS ? [m[1], m[2]] : null;
}

export async function handle(req, db) {
  try {
    if (req.method === "GET") {
      const agent = new URL(req.url).searchParams.get("agent") || "";
      if (!AGENT_ID.test(agent)) return json(400, { error: "bad_request", message: "agent must match ^[a-z0-9_-]{1,40}$" });
      return json(200, await db.status(agent));
    }
    if (req.method !== "POST") return json(405, { error: "bad_request", message: "use GET (status) or POST (actions)" });
    const auth = req.headers.get("authorization") || "";
    const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
    if (!token) return json(401, { error: "unauthorized", message: "missing Authorization: Bearer <token>" });
    const raw = await req.text();
    if (raw.length > MAX_REQUEST_CHARS) return json(413, { error: "bad_request", message: "request body too large" });
    let payload;
    try {
      payload = JSON.parse(raw || "{}");
    } catch {
      return json(400, { error: "bad_request", message: "body is not JSON" });
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload) || typeof payload.action !== "string") {
      return json(400, { error: "bad_request", message: "body must be a JSON object with an action" });
    }
    const { action, ...args } = payload;
    return json(200, await db.api(token, action, args));
  } catch (e) {
    const known = splitError(e && e.message);
    if (known) return json(HTTP_STATUS[known[0]], { error: known[0], message: known[1] });
    console.error("agent-bridge:", e);
    return json(500, { error: "internal", message: "the bridge failed; see the function logs" });
  }
}
