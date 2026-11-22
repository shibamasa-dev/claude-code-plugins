# Setting a token without Claude seeing it

Shared by the `setup` skill (Claude Code's own token) and the `add` skill (another agent's token). It writes the Vault secret `agent_bridge:<id>:token`; where the same value goes next is up to the calling skill.

Offer this only when the user asks Claude to do the token handoff, and run it only after they explicitly say yes to the hosted write (it changes a Vault secret in their Supabase project; say which project, and that it is production when it is). **Never put the value in a connector tool call (`execute_sql` and the like), in a command's output or in the chat**: the connector route makes Claude read it, and the auto-mode check blocks that as a leak. Do everything in the shell, with files only the user can read, in the session scratchpad (`<scratch>`).

## Write the Vault secret

1. Generate the value: `umask 077; openssl rand -hex 32 > <scratch>/tok`
2. If the calling skill has a step that needs `tok` first (setup saves it as the plugin's setting), do it now. When it fails, stop, tell the user, and don't touch Vault (the two would differ).
3. Build the SQL inside the shell, never printing it: `umask 077; { printf "SELECT count(*) AS updated FROM (SELECT vault.update_secret(id, '"; tr -d '\n' < <scratch>/tok; printf "') FROM vault.secrets WHERE name='agent_bridge:<id>:token') u;\n"; } > <scratch>/q.sql`
4. Run it with the user's logged-in Supabase CLI (3.x): `supabase db query --remote=<project-ref> --yes -f <scratch>/q.sql 2>&1 | grep -o '"updated"[^,}]*'`. Without `--yes` the CLI refuses in agent mode (`HostedMutationConsentRequiredError`), so `--yes` is the user's explicit OK, not a default. The filter keeps the value out of the output. `"updated": 1` means one secret was written; `0` means no secret has that name (register the agent first); no output at all is a failure. Don't show the raw output, retry once with the same `tok`, and if it still fails use the clipboard route below. The count says a write happened, not that the value is right: the authenticated call below is the proof.
5. Delete the SQL file: `rm -f <scratch>/q.sql`. Keep `<scratch>/tok` until the calling skill's check has passed (for another agent, until the agent itself has confirmed `me`, not just until the clipboard step), then `rm -f <scratch>/tok`. Deleted too early, the token has to be regenerated and written again.

With several agents, handle one at a time: make and write one token, have the user paste it into that agent, confirm it, and only then start the next.

When the CLI is missing or logged out, copy the value instead: `pbcopy < <scratch>/tok` (macOS), and the user pastes it into the Vault secret in the dashboard (`https://supabase.com/dashboard/project/<project-ref>/integrations/vault/secrets?search=<id>`; each row's ⋮ menu at the far right, which may need horizontal scrolling, then Edit. Older dashboards: Project Settings → Vault or Integrations → Vault). Keep `tok` until the check has passed, then delete it. Without a clipboard tool, fall back to the manual steps in the calling skill.

## Authenticated call from the shell

Proves that the Vault secret equals `tok`, with the token kept out of argv: `umask 077; printf 'Authorization: Bearer %s' "$(tr -d '\n' < <scratch>/tok)" > <scratch>/hdr`, then `curl -s -X POST <bridge_url> -H @<scratch>/hdr -H 'Content-Type: application/json' -d '{"action":"participants"}'`, then `rm -f <scratch>/hdr`. The answer's `me` must be the agent's id, and `participants` lists everyone on the bridge. `unauthorized` means the Vault secret differs from `tok`. The first call can take about 30 seconds (the Edge Function starts cold). An HTTP 400 such as `agent must match ^[a-z0-9_-]{1,40}$` is not a sign that the token works: that check runs before authentication. Only `me` proves it.

## Until a secret is replaced

The bridge treats a `REPLACE_ME` secret as unset: a placeholder token authenticates no one, and a webhook agent's messages are stored with `delivery = not_configured` instead of being POSTed.
