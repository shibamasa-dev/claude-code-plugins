# spotify

English | [日本語](README.ja.md)

Skills that drive your own Spotify through the Web API: choose a device and play, move playback, see what is playing and what you played recently, read your playlists, add tracks without duplicates, check Liked Songs, and have Claude recommend tracks from the taste in your playlists, then add the ones you liked.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install spotify@shibamasa-plugins
```

Then ask Claude to set up Spotify; the `setup` skill walks through the rest.

## Skills

| Skill | Use it for |
|---|---|
| `spotify` | "Play ... on Spotify", "play something I'd like", "what's playing", "move playback to my phone", "add this to my playlist". Commands: `devices`, `play`, `transfer`, `now`, `recent`, `playlists`, `tracks`, `taste`, `search`, `add` (skips tracks already in the playlist), `liked`, `check`, `auth`. The script is `skills/spotify/scripts/spotify.py` (Python, standard library only) and prints JSON, never a token. For recommendations Claude reads `taste`, picks tracks itself (Spotify's `/recommendations` is closed to new apps), plays them, and later adds the ones you saved to Liked Songs |
| `setup` | First-time setup and re-authorization: create a Spotify developer app (Redirect URI `http://127.0.0.1:<redirect_port>/callback`, Web API), open the Spotify app on the device to play on, run the first browser authorization with your own Client ID, and confirm with `check` and `devices` |

## How auth works

Authorization Code with PKCE, so there is no Client Secret anywhere. `auth` opens Spotify's consent page in your browser and listens on `127.0.0.1:<redirect_port>` for the callback; the client ID, refresh token and access token then go to the token store. The access token lasts an hour and the script renews it when it has expired, writing back a new refresh token when Spotify returns one. With the `file` store it checks that the token directory can be written before it asks Spotify for new tokens, so a sandbox that blocks writes stops the command before a rotated refresh token is received. A write that still fails after that (or an `op item edit` that fails with the `1password` store) may lose the new refresh token; authorizing again recovers.

The refresh token expires 6 months after you authorized, and refreshing the access token does not extend it. After that, commands fail with `invalid_grant` and the `setup` skill runs `auth` again.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `token_store` | `file` | Where the client ID and tokens live. `file`: one JSON file, mode 0600, in a directory with mode 0700. `1password`: one 1Password item, read and written through the `op` CLI |
| `op_item` | `Spotify Web API` | Title of the 1Password item (`1password` only). The first `auth` creates it. No single quotes (the skills pass it inside single quotes) |
| `op_vault` | empty | Vault of that item (`1password` only). Empty means every vault when reading and `op`'s default vault when creating. No single quotes |
| `redirect_port` | `8888` | Port of the Redirect URI registered in your developer app. Change both together |

Commands Claude runs through Bash get none of these on their own, so the skills pass them to the script as environment variables. A value that still reads as a `${user_config...}` placeholder counts as unset and takes the default.

### Where files go

| File | Place | What it is |
|---|---|---|
| `token.json` | `${CLAUDE_PLUGIN_DATA}/spotify/` | The client ID, refresh token, access token and its expiry (`file` store). Written through a temp file in the same directory and renamed into place |

`${CLAUDE_PLUGIN_DATA}` is `~/.claude/plugins/data/spotify-<marketplace>/`. The script refuses to run the `file` store when `CLAUDE_PLUGIN_DATA` is not this plugin's directory, instead of writing the tokens to a second place. With the `1password` store nothing is written to disk.

Uninstalling the plugin from the last place it is installed deletes `${CLAUDE_PLUGIN_DATA}`, and the token with it, unless you pass `--keep-data`. A 1Password item is not touched; delete it yourself if you no longer want it. To revoke the authorization itself, remove the app at https://www.spotify.com/account/apps/.

## Limitations

- Your own account only: the developer app is in Development Mode, which needs the app owner to have Spotify Premium and allows at most 5 users.
- Playback control (`play`, `transfer`) needs Premium. Only devices with the Spotify app open can be played on.
- Only your own and collaborative playlists can be read or added to. There is no command to remove tracks.
- No `/recommendations`, related artists or audio features: Spotify closed them to apps created on or after 2024-11-27, so Claude picks the tracks.
- "Liked" means saved to Liked Songs. Whether you played a track to the end is not used.
- Inside Claude Code's Bash sandbox, `op` does not work and writing the token file may be blocked. The skills tell Claude to run those commands outside the sandbox.
- Some behaviour is mocked from Spotify's reference but not yet checked against a real account: the order of Liked Songs, the 204 from now playing, and the reason names of the 404 and 403 playback errors (see `skills/spotify/references/api-notes.md`).

## Requirements

- A Spotify account with Premium (the developer app owner)
- Python 3.9 or later (standard library only)
- A browser on the same machine for `auth`
- The 1Password CLI (`op`) with the desktop app integration, only for the `1password` store

## Tests

```bash
bash plugins/spotify/tests/run-all.sh
```

Offline: each case runs the script against a mock Spotify on 127.0.0.1 with a temp plugin data directory, and `PATH` holds only a recording `op` stub and the system directories, so neither the real Spotify nor 1Password is reached. The cases cover playing and moving playback by device name, adding with duplicate skipping and 100-track chunks, refusing ambiguous or foreign playlists, Liked Songs since a time, refresh and write-back without printing tokens, player errors and 429 retries, `taste`, PKCE `auth` (wrong state refused, tokens saved, then `check` with the stored token), keeping the old client ID and tokens when switching to another app fails, `token.json` at mode 600 in a 700 directory under umask 022, the `1password` store calling `op` with the item JSON on stdin, unsubstituted `${user_config...}` values falling back to the `file` store, refusing a foreign or unsubstituted `CLAUDE_PLUGIN_DATA`, an unknown `token_store`, stopping before a refresh when the store can't be written, refusing a device without an ID, keeping `is_playing` during an ad, stopping on a long `Retry-After` instead of resending early, a malformed token response, and replacing a broken `token.json` with `auth --client-id`. The auth callback uses a free port per case.
