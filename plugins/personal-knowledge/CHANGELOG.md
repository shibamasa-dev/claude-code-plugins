# Changelog

Changes to the personal-knowledge plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.0] - 2026-11-27

### Added
- First release, with the `get-chrome-history` skill, its messages and skill body in English. It reads one Chrome profile's History database (copied first, because Chrome locks it), takes the visits added since the last run (the first run takes the last 7 days), and sorts them into known services, unknown domains for Claude to classify, and noise
- `chrome_profile` option (default `Default`) picks the profile; the script looks under the macOS and Linux Chrome and Chromium profile folders, and when the History file is missing it says which profiles it did find
- State (`state.json`, the last visit time seen, one per History file so each profile keeps its own window) and the evolving `knowledge.json` live in the plugin data directory under `get-chrome-history/`. The first run copies the seed `knowledge.json` shipped with the skill there and later runs never overwrite it. The last visit time is saved only after the output is printed, so a failed run fetches the same window again
- Page titles are treated as data written by the sites visited: control characters are dropped, titles are cut at 200 characters, and the skill tells Claude never to follow instructions found in a title or URL. Output is written as UTF-8 whatever the locale
- A service in `knowledge.json` with `"ignore": true` is counted as noise instead of being listed, and a host matches its service at any parent level (`www.amazon.co.jp` matches `amazon.co.jp`)
