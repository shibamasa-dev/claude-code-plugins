# Changelog

Changes to the spotify plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.0] - 2026-11-28

### Added
- First release, with messages and skill bodies in English. The `spotify` skill drives your own Spotify through the Web API with Authorization Code + PKCE (no client secret): devices, playing on a chosen device, moving playback, now playing, recently played, your playlists and their tracks, `taste` (top artists and recent additions per playlist), search, adding tracks without duplicates (100 per request), and Liked Songs since a time. It runs the recommend → play → add-what-you-liked flow, judging "liked" by Liked Songs only
- The `setup` skill: creating the developer app, opening Spotify on a device, the first `auth` with your own Client ID, and confirming with `check` and `devices`
- `token_store` option: `file` (default) keeps the client ID and tokens in `${CLAUDE_PLUGIN_DATA}/spotify/token.json` with mode 0600 in a 0700 directory, written through a temp file and a rename; `1password` keeps them in one 1Password item through `op`, passing the item JSON on stdin. `op_item`, `op_vault` and `redirect_port` options. Values still reading as `${...}` placeholders count as unset
- With the file store, the script checks that the token directory can be written before asking Spotify for new tokens (`store_not_writable`), and refuses the file store when `CLAUDE_PLUGIN_DATA` is not this plugin's directory, so tokens are not split across two places. A write that fails later reports `store_write_failed`
- Offline tests (`tests/run-all.sh`) against a mock Spotify and a recording `op` stub
