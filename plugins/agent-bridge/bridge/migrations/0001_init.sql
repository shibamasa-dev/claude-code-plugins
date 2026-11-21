-- agent-bridge 0001: the message queue, the participant list and every rule that must hold on a write.
-- Postgres on Supabase (needs the pg_net and Vault extensions). Idempotent: running it again changes nothing
-- that exists, and never touches a Vault secret.
--
-- Everything lives in its own schema, agent_bridge, which the Data API does not expose. Only the Edge Function
-- reaches it, over the database connection, through agent_bridge.api() and agent_bridge.status().

-- pg_net is available on every Supabase project. The check keeps the file runnable on a Postgres without it
-- (the tests provide stand-ins for net and vault there).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pg_net') THEN
    CREATE EXTENSION IF NOT EXISTS pg_net;
  END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS agent_bridge;
REVOKE ALL ON SCHEMA agent_bridge FROM PUBLIC;

CREATE TABLE IF NOT EXISTS agent_bridge.schema_migrations (
  version    text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_bridge.participants (
  agent_id     text PRIMARY KEY CHECK (agent_id ~ '^[a-z0-9_-]{1,40}$'),
  display_name text NOT NULL DEFAULT '',
  role         text NOT NULL DEFAULT '',
  capabilities text NOT NULL DEFAULT '',
  wake         text NOT NULL CHECK (wake IN ('poll', 'webhook')),
  active       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_bridge.threads (
  thread_id    text PRIMARY KEY CHECK (thread_id ~ '^[a-z0-9_-]{1,80}$'),
  purpose      text NOT NULL DEFAULT '',
  created_by   text NOT NULL,
  status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  max_messages integer NOT NULL DEFAULT 20 CHECK (max_messages > 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_bridge.messages (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  thread_id  text NOT NULL REFERENCES agent_bridge.threads (thread_id),
  from_agent text NOT NULL REFERENCES agent_bridge.participants (agent_id),
  to_agent   text NOT NULL REFERENCES agent_bridge.participants (agent_id),
  body       text NOT NULL CHECK (length(body) BETWEEN 1 AND 20000),
  delivery   text NOT NULL CHECK (delivery IN ('poll', 'queued', 'not_configured')),
  request_id bigint,           -- pg_net request id when delivery = 'queued'
  claimed_at timestamptz,      -- set by inbox; a claim older than 10 minutes can be taken again
  read_at    timestamptz,      -- set by ack
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (from_agent <> to_agent)
);
-- Row level security on, with no policies: the API roles see nothing even if the schema is exposed later
ALTER TABLE agent_bridge.participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_bridge.threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_bridge.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_bridge.schema_migrations ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS messages_inbox_idx ON agent_bridge.messages (to_agent, read_at, id);
CREATE INDEX IF NOT EXISTS messages_thread_idx ON agent_bridge.messages (thread_id);

-- updated_at is kept by the schema, whoever writes the row
CREATE OR REPLACE FUNCTION agent_bridge.touch() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS participants_touch ON agent_bridge.participants;
CREATE TRIGGER participants_touch BEFORE UPDATE ON agent_bridge.participants
  FOR EACH ROW EXECUTE FUNCTION agent_bridge.touch();
DROP TRIGGER IF EXISTS threads_touch ON agent_bridge.threads;
CREATE TRIGGER threads_touch BEFORE UPDATE ON agent_bridge.threads
  FOR EACH ROW EXECUTE FUNCTION agent_bridge.touch();
DROP TRIGGER IF EXISTS messages_touch ON agent_bridge.messages;
CREATE TRIGGER messages_touch BEFORE UPDATE ON agent_bridge.messages
  FOR EACH ROW EXECUTE FUNCTION agent_bridge.touch();

-- The cap on messages per thread holds for every writer, not only for api()
CREATE OR REPLACE FUNCTION agent_bridge.enforce_thread() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  t agent_bridge.threads%ROWTYPE;
  n integer;
BEGIN
  SELECT * INTO t FROM agent_bridge.threads WHERE thread_id = NEW.thread_id FOR UPDATE;
  IF t.status = 'closed' THEN
    RAISE EXCEPTION 'thread_closed: thread % is closed', NEW.thread_id;
  END IF;
  SELECT count(*) INTO n FROM agent_bridge.messages WHERE thread_id = NEW.thread_id;
  IF n >= t.max_messages THEN
    RAISE EXCEPTION 'hop_limit: thread % already has % messages (max_messages = %); ask the user before raising it',
      NEW.thread_id, n, t.max_messages;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS messages_enforce_thread ON agent_bridge.messages;
CREATE TRIGGER messages_enforce_thread BEFORE INSERT ON agent_bridge.messages
  FOR EACH ROW EXECUTE FUNCTION agent_bridge.enforce_thread();

-- Vault access. Secret names: agent_bridge:<agent_id>:token, :webhook_url, :webhook_key.
-- 'REPLACE_ME' is the placeholder setup writes; it and the empty string never count as a value.
CREATE OR REPLACE FUNCTION agent_bridge.is_set(v text) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
  SELECT v IS NOT NULL AND v <> '' AND v <> 'REPLACE_ME'
$$;

CREATE OR REPLACE FUNCTION agent_bridge.secret(p_name text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name = p_name LIMIT 1
$$;

-- Add or update a participant, and create its Vault secrets as placeholders when they don't exist yet.
-- An existing secret is never changed, so running setup again keeps the values the user entered.
CREATE OR REPLACE FUNCTION agent_bridge.register_participant(
  p_agent_id text, p_wake text, p_display_name text DEFAULT '', p_role text DEFAULT '', p_capabilities text DEFAULT ''
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  names text[];
  n text;
BEGIN
  INSERT INTO agent_bridge.participants (agent_id, wake, display_name, role, capabilities)
  VALUES (p_agent_id, p_wake, p_display_name, p_role, p_capabilities)
  ON CONFLICT (agent_id) DO UPDATE
    SET wake = EXCLUDED.wake, display_name = EXCLUDED.display_name, role = EXCLUDED.role,
        capabilities = EXCLUDED.capabilities, active = true;
  names := ARRAY['agent_bridge:' || p_agent_id || ':token'];
  IF p_wake = 'webhook' THEN
    names := names || ARRAY['agent_bridge:' || p_agent_id || ':webhook_url', 'agent_bridge:' || p_agent_id || ':webhook_key'];
  END IF;
  FOREACH n IN ARRAY names LOOP
    IF NOT EXISTS (SELECT 1 FROM vault.secrets WHERE name = n) THEN
      PERFORM vault.create_secret('REPLACE_ME', n, 'agent-bridge: replace REPLACE_ME with the real value');
    END IF;
  END LOOP;
  RETURN jsonb_build_object('agent_id', p_agent_id, 'wake', p_wake, 'secrets', to_jsonb(names));
END $$;

-- Which secrets still need a real value. Names and states only, never a value.
CREATE OR REPLACE FUNCTION agent_bridge.doctor()
RETURNS TABLE (agent_id text, secret_name text, state text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  WITH wanted AS (
    SELECT p.agent_id, 'agent_bridge:' || p.agent_id || ':token' AS n FROM agent_bridge.participants p WHERE p.active
    UNION ALL
    SELECT p.agent_id, 'agent_bridge:' || p.agent_id || ':' || k
    FROM agent_bridge.participants p CROSS JOIN (VALUES ('webhook_url'), ('webhook_key')) AS kinds (k)
    WHERE p.active AND p.wake = 'webhook'
  )
  SELECT w.agent_id, w.n,
         CASE WHEN s.name IS NULL THEN 'missing'
              WHEN agent_bridge.is_set(s.decrypted_secret) THEN 'set'
              ELSE 'placeholder' END
  FROM wanted w LEFT JOIN vault.decrypted_secrets s ON s.name = w.n
  ORDER BY w.agent_id, w.n
$$;

CREATE OR REPLACE FUNCTION agent_bridge.agent_for_token(p_token text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT p.agent_id
  FROM agent_bridge.participants p
  JOIN vault.decrypted_secrets s ON s.name = 'agent_bridge:' || p.agent_id || ':token'
  WHERE p.active AND agent_bridge.is_set(p_token) AND agent_bridge.is_set(s.decrypted_secret)
    AND s.decrypted_secret = p_token
  LIMIT 1
$$;

-- The unauthenticated check that poll-type agents call: a count and the newest id, never a body.
CREATE OR REPLACE FUNCTION agent_bridge.status(p_agent_id text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT jsonb_build_object(
    'agent', p_agent_id,
    'unread', count(*) FILTER (WHERE m.read_at IS NULL),
    'latest_id', coalesce(max(m.id), 0))
  FROM agent_bridge.messages m
  WHERE m.to_agent = p_agent_id
$$;

-- Every authenticated call. Errors are raised as '<code>: <message>'; the Edge Function maps the code to HTTP.
CREATE OR REPLACE FUNCTION agent_bridge.api(p_token text, p_action text, p_args jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  me text := agent_bridge.agent_for_token(p_token);
  a jsonb := coalesce(p_args, '{}'::jsonb);
  rcpt agent_bridge.participants%ROWTYPE;
  v_thread text;
  v_body text;
  v_url text;
  v_key text;
  v_delivery text;
  v_request bigint;
  v_id bigint;
  v_limit integer;
  m agent_bridge.messages%ROWTYPE;
  r jsonb;
BEGIN
  IF me IS NULL THEN
    RAISE EXCEPTION 'unauthorized: the token does not match any participant';
  END IF;

  IF p_action = 'send' THEN
    v_thread := a ->> 'thread';
    v_body := a ->> 'body';
    IF v_thread IS NULL OR v_body IS NULL OR a ->> 'to' IS NULL THEN
      RAISE EXCEPTION 'bad_request: send needs to, thread and body';
    END IF;
    SELECT * INTO rcpt FROM agent_bridge.participants WHERE agent_id = a ->> 'to' AND active;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'unknown_agent: no active participant %', a ->> 'to';
    END IF;
    INSERT INTO agent_bridge.threads (thread_id, purpose, created_by)
    VALUES (v_thread, coalesce(a ->> 'purpose', ''), me)
    ON CONFLICT (thread_id) DO NOTHING;
    v_delivery := 'poll';
    IF rcpt.wake = 'webhook' THEN
      v_url := agent_bridge.secret('agent_bridge:' || rcpt.agent_id || ':webhook_url');
      v_key := agent_bridge.secret('agent_bridge:' || rcpt.agent_id || ':webhook_key');
      v_delivery := CASE WHEN agent_bridge.is_set(v_url) AND agent_bridge.is_set(v_key) THEN 'queued' ELSE 'not_configured' END;
    END IF;
    INSERT INTO agent_bridge.messages (thread_id, from_agent, to_agent, body, delivery)
    VALUES (v_thread, me, rcpt.agent_id, v_body, v_delivery)
    RETURNING * INTO m;
    IF v_delivery = 'queued' THEN
      -- pg_net sends after this transaction commits; whether it arrived is read later with action 'message'
      v_request := net.http_post(
        url := v_url,
        body := jsonb_build_object('event', 'agent_bridge.message', 'id', m.id, 'thread', m.thread_id,
                                   'from', m.from_agent, 'to', m.to_agent, 'body', m.body, 'created_at', m.created_at),
        headers := jsonb_build_object('Content-Type', 'application/json', 'Authorization', 'Bearer ' || v_key),
        timeout_milliseconds := 10000);
      UPDATE agent_bridge.messages SET request_id = v_request WHERE id = m.id;
    END IF;
    RETURN jsonb_build_object('id', m.id, 'thread', m.thread_id, 'to', m.to_agent, 'delivery', v_delivery);

  ELSIF p_action = 'inbox' THEN
    v_limit := least(greatest(coalesce((a ->> 'limit')::integer, 20), 1), 100);
    WITH picked AS (
      SELECT id FROM agent_bridge.messages
      WHERE to_agent = me AND read_at IS NULL
        AND (claimed_at IS NULL OR claimed_at < now() - interval '10 minutes')
        AND (a ->> 'thread' IS NULL OR thread_id = a ->> 'thread')
      ORDER BY id
      LIMIT v_limit
      FOR UPDATE SKIP LOCKED
    ), claimed AS (
      UPDATE agent_bridge.messages x SET claimed_at = now()
      FROM picked WHERE x.id = picked.id
      RETURNING x.id, x.thread_id, x.from_agent, x.body, x.created_at
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('id', c.id, 'thread', c.thread_id, 'from', c.from_agent,
                                                 'purpose', t.purpose, 'body', c.body, 'created_at', c.created_at)
                              ORDER BY c.id), '[]'::jsonb)
    INTO r
    FROM claimed c JOIN agent_bridge.threads t ON t.thread_id = c.thread_id;
    RETURN jsonb_build_object('agent', me, 'messages', r);

  ELSIF p_action = 'ack' THEN
    IF jsonb_typeof(a -> 'ids') IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION 'bad_request: ack needs ids (an array of message ids)';
    END IF;
    WITH done AS (
      UPDATE agent_bridge.messages SET read_at = now()
      WHERE to_agent = me AND read_at IS NULL
        AND id IN (SELECT (jsonb_array_elements_text(a -> 'ids'))::bigint)
      RETURNING id
    )
    SELECT count(*) INTO v_id FROM done;
    RETURN jsonb_build_object('acked', v_id);

  ELSIF p_action = 'participants' THEN
    SELECT coalesce(jsonb_agg(jsonb_build_object('agent_id', agent_id, 'display_name', display_name, 'role', role,
                                                 'capabilities', capabilities, 'wake', wake) ORDER BY agent_id), '[]'::jsonb)
    INTO r FROM agent_bridge.participants WHERE active;
    RETURN jsonb_build_object('me', me, 'participants', r);

  ELSIF p_action = 'message' THEN
    SELECT * INTO m FROM agent_bridge.messages
    WHERE id = (a ->> 'id')::bigint AND (from_agent = me OR to_agent = me);
    IF NOT FOUND THEN
      RAISE EXCEPTION 'not_found: no message % that you sent or received', a ->> 'id';
    END IF;
    r := jsonb_build_object('id', m.id, 'thread', m.thread_id, 'from', m.from_agent, 'to', m.to_agent,
                            'delivery', m.delivery, 'claimed_at', m.claimed_at, 'read_at', m.read_at);
    IF m.request_id IS NOT NULL THEN
      r := r || coalesce(
        (SELECT jsonb_build_object('webhook_status', h.status_code, 'webhook_timed_out', h.timed_out,
                                   'webhook_error', h.error_msg)
         FROM net._http_response h WHERE h.id = m.request_id),
        jsonb_build_object('webhook_status', NULL, 'webhook_note', 'no response recorded yet (pending, or older than pg_net keeps)'));
    END IF;
    RETURN r;

  ELSE
    RAISE EXCEPTION 'bad_request: unknown action %', p_action;
  END IF;
END $$;

-- Nothing here is callable by the API roles; the Edge Function connects as the database owner.
REVOKE ALL ON ALL TABLES IN SCHEMA agent_bridge FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA agent_bridge FROM PUBLIC;
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON SCHEMA agent_bridge FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA agent_bridge FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA agent_bridge FROM %I', r);
    END IF;
  END LOOP;
END $$;

INSERT INTO agent_bridge.schema_migrations (version) VALUES ('0001_init') ON CONFLICT DO NOTHING;
