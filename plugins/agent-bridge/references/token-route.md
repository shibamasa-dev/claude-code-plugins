# Setting a token without Claude seeing it

Shared by the `setup` skill (Claude Code's own token) and the `add` skill (another agent's token). It writes the Vault secret `agent_bridge:<id>:token`; where the same value goes next is up to the calling skill.

Offer this only when the user asks Claude to do the token handoff, and run it only after they explicitly say yes to the hosted write (it changes a Vault secret in their Supabase project; say which project, and that it is production when it is). **Never put the value in a connector tool call (`execute_sql` and the like), in a command's output or in the chat**: the connector route makes Claude read it, and the auto-mode check blocks that as a leak. Do everything in the shell, with files only the user can read, in the session scratchpad (`<scratch>`).

## Write the Vault secret

1. Generate the value: `umask 077; openssl rand -hex 32 > <scratch>/tok`
2. If the calling skill has a step that needs `tok` first (setup saves it as the plugin's setting), do it now. When it fails, stop, tell the user, and don't touch Vault (the two would differ).
3. Build the SQL inside the shell, never printing it: `umask 077; { printf "SELECT vault.update_secret((SELECT id FROM vault.secrets WHERE name='agent_bridge:<id>:token'), '"; tr -d '\n' < <scratch>/tok; printf "') IS NULL AS updated;\n"; } > <scratch>/q.sql`
4. Run it with the user's logged-in Supabase CLI (3.x): `supabase db query --remote=<project-ref> --yes -f <scratch>/q.sql 2>&1 | grep -o '"updated"[^,}]*'`. Without `--yes` the CLI refuses in agent mode (`HostedMutationConsentRequiredError`), so `--yes` is the user's explicit OK, not a default. The filter keeps the value out of the output; when it prints nothing, treat that as a failure, don't show the raw output, retry once with the same `tok`, and if it still fails use the clipboard route below.
5. Delete the SQL file: `rm -f <scratch>/q.sql`. Keep `<scratch>/tok` until the calling skill's check has run (the check needs it), then `rm -f <scratch>/tok`.

When the CLI is missing or logged out, copy the value instead: `pbcopy < <scratch>/tok` (macOS), and the user pastes it into the Vault secret in the dashboard (Project Settings → Vault, or Integrations → Vault, depending on the dashboard version). Run the check, then delete `tok`. Without a clipboard tool, fall back to the manual steps in the calling skill.

## Authenticated call from the shell

Proves that the Vault secret equals `tok`, with the token kept out of argv: `umask 077; printf 'Authorization: Bearer %s' "$(tr -d '\n' < <scratch>/tok)" > <scratch>/hdr`, then `curl -s -X POST <bridge_url> -H @<scratch>/hdr -H 'Content-Type: application/json' -d '{"action":"participants"}'`, then `rm -f <scratch>/hdr`. The answer's `me` must be the agent's id, and `participants` lists everyone on the bridge. `unauthorized` means the Vault secret differs from `tok`.

## Until a secret is replaced

The bridge treats a `REPLACE_ME` secret as unset: a placeholder token authenticates no one, and a webhook agent's messages are stored with `delivery = not_configured` instead of being POSTed.
