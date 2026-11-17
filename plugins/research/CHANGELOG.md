# Changelog

Changes to the research plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.0] - 2026-11-17

### Added
- First release: the `research-x` skill and its Python CLI (standard library only). It asks xAI's X search about the accounts in the `accounts` setting, keeps clear update announcements, summarizes each in the configured language and tone, and posts one message per announcement to the `slack_channel` setting
- The channel history is the only state: each run takes the previous run's start time from message metadata and skips status IDs already quoted in the channel
- Fail closed: if any xAI request fails, nothing is posted and the run exits 1. `--dry-run` never posts
- Credentials come from the environment (`XAI_API_KEY`, `SLACK_BOT_TOKEN`), not from `userConfig`
