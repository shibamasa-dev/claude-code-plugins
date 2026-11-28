# Spotify Web API notes (checked against the official docs on 2026-11-28)

The script follows these points. When something behaves oddly, first check whether the sources below have changed.

## Not available

- **`/recommendations`, related artists, audio features and analysis, and fetching Spotify's own recommendation playlists** are unavailable to apps created on or after 2024-11-27 and to Development Mode apps without extended access. Claude picks the recommendations.
  Source: https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api
- Playlists made by Spotify and algorithmic playlists can't be read (same source).

## The 2026-02 changes (Development Mode)

Sources: https://developer.spotify.com/documentation/web-api/references/changes/february-2026 and https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide

- Playlist tracks moved from `/playlists/{id}/tracks` (removed) to **`/playlists/{id}/items`** (GET, POST, PUT, DELETE). Each entry's track is `items[].item` (formerly `items[].track`).
- Only **owned and collaborative playlists** can be read. Other people's return 403 (metadata only).
- The track count in the list (`/me/playlists`) is `items.total` (formerly `tracks.total`).
- `GET /me/tracks` (Liked Songs) still works. Each entry has `added_at` and `track` (a different name from the playlist's `item`). **The reference does not say the list is newest first (unverified).** `liked --since` assumes newest first and stops reading at the first older entry. Check this first on a real account.
- Saving and removing Liked Songs moved to `PUT/DELETE /me/library` (this plugin does not use them).
- Search (`/search`) allows `limit` up to 10, default 5.
- Artist `popularity` and `followers`, track `popularity` and similar fields are no longer returned.
- The app owner must have Premium. At most 5 users. Since 2026-07 a developer account can have 25 apps, and the quota counts per developer account; going over returns 429 with `reason: QUOTA_EXCEEDED`.
  Source: https://developer.spotify.com/documentation/web-api/references/changes/july-2026

## Playback

- Playing (`PUT /me/player/play`) and moving playback (`PUT /me/player`) need Premium. Success is 204. Without `device_id`, the active device.
- `device_ids` for moving playback takes exactly one ID (two or more return 400).
- The device list holds only devices with Spotify running. A device with `is_restricted: true` accepts no Web API commands. Device IDs can change, so look them up every time (the script looks them up by name).
- The reference for now playing (`/me/player/currently-playing`) lists only a 200 response, and `item` may be null. Whether an empty 204 comes back when nothing plays is unverified. The script treats both as not playing.
- The 404 `NO_ACTIVE_DEVICE` with no active device and the 403 `PREMIUM_REQUIRED` without Premium are not in the playback reference (unverified). The script passes the error body's `reason` to stderr as it is.
- Recently played has only `played_at`, not how far a track was played (why it is not used to judge "liked"). At most 50 entries; `after` and `before` are Unix times in milliseconds.

## Auth

- Redirect URIs must be HTTPS, except loopback: `http://127.0.0.1:PORT` or `http://[::1]:PORT`. **`localhost` is not allowed.**
  Source: https://developer.spotify.com/documentation/web-api/concepts/redirect_uri
- A refresh response does not always carry a new refresh token. When it does, replace the old one; otherwise keep using it. `invalid_grant` means authorizing again.
  Source: https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens
- The plugin uses Authorization Code + PKCE, so it never handles a Client Secret. The authorize URL carries `code_challenge_method=S256` and `code_challenge`; the token exchange and the refresh put `client_id` in the body (the exchange also `code_verifier`), with no Basic auth.
  Source: https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow
- With PKCE, a refresh may return a new refresh token every time. The script writes it back to the token store, and checks that the store is writable before it asks for one. Whether the old refresh token still works when a write-back fails is not documented (unverified); if not, authorizing again is the way out.
- The refresh token's lifetime is set in the developer app ("Refresh Token Lifetime" in the dashboard). After it, `invalid_grant`.
