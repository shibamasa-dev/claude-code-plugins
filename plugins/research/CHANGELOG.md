# Changelog

Changes to the research plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.2.0] - 2026-11-27

### Added
- The `read-x-article` skill: reads an X post, long post or X Article from its URL through the fxtwitter API (WebFetch gets a 402 from x.com), falls back to tool.lu when fxtwitter gives no body or a cut-short one, and summarizes it in the user's language. Instructions only, no script
- `save_dir` setting: the folder read-x-article saves a Markdown copy to, only when the user asks. Empty (the default) means it never saves. If that folder has an `INDEX.md`, one line is added to it in the format it already uses; no index is created

### Changed
- `accounts` is no longer required when enabling the plugin (default empty), so read-x-article works without it. research-x still needs it: with it empty, research-x stops and asks the user to set it

## [0.1.0] - 2026-11-17

### Added
- First release: the `research-x` skill and its Python CLI (standard library only). It asks xAI's X search about the accounts in the `accounts` setting, keeps clear update announcements, summarizes each in the configured language and tone, and posts one message per announcement to the `slack_channel` setting
- The channel history is the only state: each run takes where to search from out of message metadata and skips status IDs already quoted in the channel. A run that died while posting is completed by the next plain run
- Fail closed: if any xAI request fails, nothing is posted and the run exits 1. `--dry-run` never posts
- Credentials come from the environment (`XAI_API_KEY`, `SLACK_BOT_TOKEN`), not from `userConfig`
