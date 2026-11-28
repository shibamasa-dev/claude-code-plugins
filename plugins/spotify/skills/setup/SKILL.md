---
name: setup
description: "First-time setup of the spotify plugin, and re-authorization when Spotify's permission has expired: create a Spotify developer app with the right Redirect URI, open the Spotify app on the device to play on, run the first browser authorization with the user's own Client ID, and confirm with check and devices. Use it when the spotify skill exits 3 because nothing is stored yet or with invalid_grant, or for \"set up Spotify\", \"connect my Spotify\", \"Spotify authorization expired\", or in Japanese 「Spotify を使えるようにして」「Spotify の初期設定」「Spotify と連携して」「Spotify の許可をやり直して」「Spotify の認証が切れた」."
---

# Spotify setup

Walk the user through these steps in order. The user does steps 1 and 2 in their own accounts; you run steps 3 and 4. The Client ID belongs to the user's developer app: ask them for it, and never make one up or reuse one from elsewhere. The flow is PKCE, so **no Client Secret is used** anywhere.

Settings in effect now: token store `${user_config.token_store}`, redirect port `${user_config.redirect_port}`. A value still reading as a `${user_config...}` placeholder means the default (`file`, `8888`).

## 1. Open Spotify on the device to play on

Only devices with the Spotify app running and signed in appear in the device list. To play on this computer, install the Spotify desktop app and sign in. Phones and speakers work the same way: they are listed while the app is open.

## 2. Create a Spotify developer app

1. Sign in at https://developer.spotify.com/dashboard with the Spotify account and accept the terms.
2. Press "Create app" and fill in:
   - App name and App description: anything
   - **Redirect URI**: `http://127.0.0.1:<port>/callback`, with the redirect port above (`http://127.0.0.1:8888/callback` by default). Spotify rejects `localhost`; write the numbers `127.0.0.1`. If the port is taken on this machine, pick another, register that one, and set the plugin's `redirect_port` option to the same number (then `/reload-plugins`)
   - Which API/SDKs are you planning to use?: **Web API**
3. In the app's "Settings", copy the **Client ID** (it is not secret) and The authorization lasts 6 months from step 3 (refreshing does not extend it); after that, step 3 has to be done again.

Development Mode limits:
- The app owner's account must have **Spotify Premium** (the app stops working when it lapses). Playback control needs Premium too.
- At most 5 users, the owner included. Using it alone needs no extra settings.

## 3. Authorize in the browser

Only with token store `1password`, before running `auth` (the user does these in 1Password; the script only ever uses a service account, so no command waits for Touch ID or a password):

1. Create a vault just for this, for example `Spotify`. A service account can't use the Personal (Private) vault, and vaults can't be added to it later, so the vault comes first.
2. Create a service account (on 1Password.com: Developer → Service Accounts) with **read and write** access to that vault only. Write access is needed because Spotify may hand out a new refresh token on every refresh.
3. Put the service account token in an environment variable of the user's choosing (for example `SPOTIFY_OP_SA_TOKEN`) in the environment Claude Code starts with, for example exported by the shell profile, then restart Claude Code. Never paste the token into the chat or into a plugin option.
4. Set the plugin's options: `op_vault` to the vault, `op_token_env` to the variable's **name**, then `/reload-plugins`.

`auth` creates the item (title from `op_item`) and prints `op_item_id`; setting `op_item` to that ID saves requests. Individual and Families accounts allow 1,000 service account requests a day in total. Every command calls `op` once to read the item, and one that refreshes the token (about once an hour) calls it again to write; how many requests one `op` call counts as is not documented here.

Run this **outside Claude Code's Bash sandbox** (`dangerouslyDisableSandbox: true`): it opens the browser, listens on 127.0.0.1 for Spotify's callback, and writes the token store, all of which the sandbox may block. Give it a timeout of at least 310 seconds (it waits up to 300 for the callback), or run it in the background and read its output.

```bash
CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' SPOTIFY_TOKEN_STORE='${user_config.token_store}' SPOTIFY_OP_ITEM='${user_config.op_item}' SPOTIFY_OP_VAULT='${user_config.op_vault}' SPOTIFY_OP_TOKEN_ENV='${user_config.op_token_env}' SPOTIFY_REDIRECT_PORT='${user_config.redirect_port}' python3 "${CLAUDE_PLUGIN_ROOT}/skills/spotify/scripts/spotify.py" auth --client-id <Client ID>
```

The browser opens Spotify's consent page; the user presses "Agree". If no browser opens, the script prints the URL on stderr: give it to the user to open. `{"ok": true, ...}` means the token store now holds the refresh token, and from then on the script renews the hour-long access token by itself.

To authorize again (the refresh token expired, the user revoked access, or the scopes changed), run the same command without `--client-id`.

## 4. Confirm

```bash
CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' SPOTIFY_TOKEN_STORE='${user_config.token_store}' SPOTIFY_OP_ITEM='${user_config.op_item}' SPOTIFY_OP_VAULT='${user_config.op_vault}' SPOTIFY_OP_TOKEN_ENV='${user_config.op_token_env}' SPOTIFY_REDIRECT_PORT='${user_config.redirect_port}' python3 "${CLAUDE_PLUGIN_ROOT}/skills/spotify/scripts/spotify.py" check
CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' SPOTIFY_TOKEN_STORE='${user_config.token_store}' SPOTIFY_OP_ITEM='${user_config.op_item}' SPOTIFY_OP_VAULT='${user_config.op_vault}' SPOTIFY_OP_TOKEN_ENV='${user_config.op_token_env}' SPOTIFY_REDIRECT_PORT='${user_config.redirect_port}' python3 "${CLAUDE_PLUGIN_ROOT}/skills/spotify/scripts/spotify.py" devices
```

Setup is done when `check` shows a user ID and `devices` lists the device from step 1. Both only read; nothing in the account changes. Then the spotify skill takes over.

## When it fails

| What you see | What to do |
|---|---|
| Exit 3 with `reason: store_not_writable` | The command ran inside the sandbox. Run it again outside |
| Exit 3 with `reason: store_write_failed` | The new tokens were received but not saved. Run the command again outside the sandbox; if it then fails with `invalid_grant`, do step 3 again |
| `op timed out` | No network access to 1Password, for example inside the sandbox: run it outside |
| Exit 3 with `reason: op_token_missing` | `op_token_env` is empty, or the variable it names is not set where Claude Code runs: set it and restart Claude Code |
| Exit 2 with `reason: op_token_env_invalid` | `op_token_env` holds something other than a variable name, perhaps the token itself: put the name there and rotate the token if it was the token |
| `invalid_grant` | 6 months passed since the authorization, or access was revoked: step 3 again, without `--client-id` |
| Spotify's page says the redirect URI is invalid | The Redirect URI in the dashboard differs from `http://127.0.0.1:<redirect port>/callback` |
| `Address already in use` | The redirect port is taken: change it in the dashboard and in `redirect_port` together |

To revoke the authorization, remove the app at https://www.spotify.com/account/apps/.
