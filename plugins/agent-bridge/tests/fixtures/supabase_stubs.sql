-- Stand-ins for the parts of Supabase that plain Postgres lacks, with the signatures the bridge uses
-- (from the Supabase docs for Vault and pg_net). net.http_post records the call instead of sending it.
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;

CREATE SCHEMA vault;
CREATE TABLE vault.secrets (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text UNIQUE,
  secret      text NOT NULL,
  description text NOT NULL DEFAULT ''
);
CREATE VIEW vault.decrypted_secrets AS
  SELECT id, name, secret AS decrypted_secret, description FROM vault.secrets;
CREATE FUNCTION vault.create_secret(new_secret text, new_name text DEFAULT NULL, new_description text DEFAULT '')
RETURNS uuid LANGUAGE sql AS $$
  INSERT INTO vault.secrets (name, secret, description) VALUES (new_name, new_secret, new_description) RETURNING id
$$;

CREATE SCHEMA net;
CREATE TABLE net.calls (
  id bigserial PRIMARY KEY, url text, body jsonb, params jsonb, headers jsonb, timeout_milliseconds integer
);
CREATE TABLE net._http_response (
  id bigint, status_code integer, content text, timed_out boolean, error_msg text, created timestamptz DEFAULT now()
);
CREATE FUNCTION net.http_post(url text, body jsonb DEFAULT '{}'::jsonb, params jsonb DEFAULT '{}'::jsonb,
                              headers jsonb DEFAULT '{"Content-Type": "application/json"}'::jsonb,
                              timeout_milliseconds integer DEFAULT 2000)
RETURNS bigint LANGUAGE sql AS $$
  INSERT INTO net.calls (url, body, params, headers, timeout_milliseconds)
  VALUES (url, body, params, headers, timeout_milliseconds) RETURNING id
$$;
