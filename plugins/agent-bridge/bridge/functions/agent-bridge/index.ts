// agent-bridge Edge Function (Supabase, Deno). Deploy with JWT verification off: it authenticates each caller
// itself with the per-agent token kept in Vault, and the unauthenticated GET returns counts only.
// It connects to the database with SUPABASE_DB_URL, which Supabase provides to every Edge Function,
// one connection per instance, so a busy bridge cannot crowd out the project's other clients.
import postgres from "npm:postgres@3.4.5";
import { handle } from "./router.mjs";

const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, { prepare: false, max: 1, idle_timeout: 20 });

const db = {
  async status(agent: string) {
    const [row] = await sql`SELECT agent_bridge.status(${agent}) AS r`;
    return row.r;
  },
  async api(token: string, action: string, args: Record<string, unknown>) {
    const [row] = await sql`SELECT agent_bridge.api(${token}, ${action}, ${sql.json(args)}) AS r`;
    return row.r;
  },
};

Deno.serve((req: Request) => handle(req, db));
