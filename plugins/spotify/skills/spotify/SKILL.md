---
name: spotify
description: "Drives the user's own Spotify through the Web API: devices that can play, playing a track or playlist on a chosen device, moving playback to another device, now playing and recently played, the user's playlists and their tracks, adding tracks to a playlist, and checking Liked Songs. Also runs the flow that reads the user's taste from their playlists, recommends and plays tracks, and adds the ones they liked to a playlist. Use it for \"play ... on Spotify\", \"play something I'd like\", \"what's playing\", \"move playback here\", \"add this to my playlist\", or in Japanese 「Spotify で〜かけて」「おすすめ流して」「〇〇っぽい曲を探して再生して」「今なに流れてる？」「最近聴いた曲」「スマホ（Mac・スピーカー）で再生して」「再生をこっちに移して」「このプレイリストに足して」「気に入った曲をプレイリストに入れて」「私の好みを分析して」. The claude.ai Spotify connector cannot control playback or add to existing playlists, so do those here. Not for other music services (Apple Music, YouTube Music). First-time setup is the setup skill."
---

# spotify

One script, `scripts/spotify.py`, calls the Spotify Web API. It prints JSON and never prints a token.

## Running it

Every command is this line with the command at the end. Pass the variables exactly as written: commands run through Bash get none of the plugin's settings on their own.

```bash
CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' SPOTIFY_TOKEN_STORE='${user_config.token_store}' SPOTIFY_OP_ITEM='${user_config.op_item}' SPOTIFY_OP_VAULT='${user_config.op_vault}' SPOTIFY_REDIRECT_PORT='${user_config.redirect_port}' python3 "${CLAUDE_PLUGIN_ROOT}/skills/spotify/scripts/spotify.py" <command> [...]
```

- Auth is Authorization Code + PKCE, with no Client Secret. The client ID and tokens live in one token store: `token_store` `file` (default) keeps them in `token.json` (mode 0600) in the plugin's data directory, `1password` in one 1Password item read through `op`. The access token lasts an hour; the script refreshes it only when it has expired and writes it back (and a new refresh token, when one comes back).
- **Claude Code's Bash sandbox.** With the `file` store, reading works inside the sandbox, but writing (a refresh, about once an hour) may not: the script then exits 3 with `reason: store_not_writable` before asking Spotify for anything. Run the same command again outside the sandbox (`dangerouslyDisableSandbox: true`). With the `1password` store, always run outside the sandbox, because `op` times out inside it; it also times out while 1Password is locked, so ask the user to unlock it.
- Exit code 3 means auth is missing, expired or the store can't be used. When the error says the store has nothing yet, or `reason` is `invalid_grant`, hand over to the setup skill (the Client ID is the user's; never make one up).
- **The refresh token expires** after the developer app's "Refresh Token Lifetime" (shown in the Spotify dashboard). Then commands fail with `reason: invalid_grant` and exit 3: tell the user "Spotify's authorization has expired, please approve it in the browser again" and run `auth` as the setup skill describes (no `--client-id` needed this time). The API gives no way to see the expiry coming.

| Command | What it does |
|---|---|
| `check` | Whether auth works (prints only the user ID and display name) |
| `devices` | Devices that can play (Spotify Connect). **Only devices with the Spotify app open are listed** |
| `play [--device NAME] (--uris U… \| --context URI [--offset-uri U])` | Play. The device name matches partially; without it, the active device |
| `transfer --device NAME [--play]` | Move playback to another device |
| `now` | What is playing now |
| `recent [--limit 20] [--after ISO_TIME]` | Recently played tracks, newest first |
| `playlists [--all]` | The user's playlists (default: owned and collaborative; `--all` adds followed playlists of others) |
| `tracks <PLAYLIST>` | Tracks in a playlist. Name, ID, URI or URL |
| `taste [--playlist …]` | Per playlist, the most frequent artists and the recently added tracks (the entry point for reading taste) |
| `search "<QUERY>" [--limit 5]` | Find tracks to get URIs. Narrow with `track:<title> artist:<artist>`. At most 10 results |
| `add <PLAYLIST> <URI…>` | Add tracks. **Tracks already in the playlist are skipped** (the API allows duplicates, so the script filters them) |
| `liked [--since ISO_TIME] [--among URI…]` | Tracks saved to Liked Songs. `--among` keeps only the given tracks that were saved |
| `auth [--client-id ID]` | Approve in the browser (the user does it: first time, and when the refresh token expires). See the setup skill |

## Recommend → play → add the ones they liked

1. **Read the taste.** Run `taste` and describe, per playlist, the tendency (artists, era, language, tempo). If the user gave a direction ("something calm"), narrow to the fitting playlist (`--playlist`).
2. **Choose.** Picking tracks is your judgement. Spotify's `/recommendations` (and related artists and audio features) is unavailable to apps created on or after 2024-11-27, so the API can't do it. Mix 5 to 10 tracks: tracks not yet in the playlists by artists that appear often, and tracks by similar artists. Leave out tracks already in the playlists (`tracks`).
3. **Turn them into URIs.** `search "track:<title> artist:<artist>"`, and check that the returned artist is the intended one (same-titled songs and covers mix in). Where the claude.ai Spotify connector is available, its search (which can search by taste) may widen the candidates. When a track can't be found, say so; don't quietly substitute another.
4. **Pick the playlist to add to** before playing, and tell the user in one line (the playlist the direction came from, or the one the user named). If you can't decide, ask.
5. **Play.** Check `devices`, then `play --device <NAME> --uris <URI…>`. When no device is listed, ask the user to open the Spotify app on the device they want to hear it on. Note in the conversation the time playback started (ISO 8601) and the URIs you recommended (don't write files into the skill directory).
6. **Add the ones they liked.** When the user has finished listening, asks "how was it?", or moves on to the next recommendation, run `liked --since <time playback started> --among <recommended URIs…>` and add what comes back with `add <playlist> <URI…>`. The user asked for liked tracks to be added, so no per-track confirmation. Report what was added and what was skipped as a duplicate.

### What "liked" means

**Only Liked Songs counts. Whether a track was played to the end does not.**

- Recently played (`/me/player/recently-played`) has only `played_at`, not how far the track was played or whether it was skipped. Guessing from the gap to the next track breaks on a pause or a seek, and a wrong guess would change the user's playlist on its own, so it is not used.
- Saving to Liked Songs is something the user did on purpose; it can't be mistaken.
- Played or not may still guide the next recommendation (`recent`).

## Rules

- Playing, switching devices and adding to playlists change the user's real Spotify. Do them only when the user asks. There is no command to remove tracks from a playlist, and none should be added.
- Only owned and collaborative playlists can be added to, and only those can be read (other people's playlists return 403).
- Reading errors (the stderr JSON's `status` and `reason`; the 404 and 403 reason names below are not in the reference and are unverified, so read the actual `reason`):
  - `NO_ACTIVE_DEVICE` (404): no active device. Pass `--device`, or ask the user to open Spotify on a device
  - `PREMIUM_REQUIRED` (403): playback control needs Premium
  - 429 (including `QUOTA_EXCEEDED`): too many requests. The script waits briefly and retries twice, then stops. Wait before trying again
  - Exit 3: auth or the store, as above
- The API changed a lot in 2026-02 (playlist tracks are `/playlists/{id}/items` with an `item` field, search returns at most 10, Development Mode needs the app owner to have Premium and allows 5 users). The changes and their sources are in `references/api-notes.md`.

## Tests

`bash "${CLAUDE_PLUGIN_ROOT}/tests/run-all.sh"` runs the script against a local mock Spotify and a recording `op` stub. It touches neither 1Password nor the real Spotify.
