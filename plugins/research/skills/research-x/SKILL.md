---
name: research-x
description: Runs research-x once by hand. It asks xAI's X search about the X accounts in the plugin's settings, keeps clear update announcements, summarizes each one, and posts one Slack message per announcement to the configured channel. Always a dry run first; posts only when the user asks for it. Use for "run research-x", "check X for release announcements", "what did the accounts announce since yesterday", "post the X updates to Slack", "research-x didn't post today", or in Japanese 「research X 回して」「X の巡回を手で走らせて」「X のアップデート告知を今拾って」「Slack に流れてない」. Not for setting up a schedule (use your own scheduler).
---

# research-x (manual run)

The work is done by `scripts/research_x.py` (Python 3.9+, standard library only). This skill sets its settings and runs it. It keeps no state: the Slack channel's history is the state.

## Settings

Saved settings: accounts = `${user_config.accounts}`, channel = `${user_config.slack_channel}`, language = `${user_config.summary_language}`, tone = `${user_config.tone}`, topic = `${user_config.topic_filter}`, timezone = `${user_config.timezone}`, model = `${user_config.model}`. A value that still reads as a `${user_config...}` placeholder counts as empty (the script treats it the same way).

- If accounts is empty, stop and ask the user to set the plugin's `accounts` option (`/plugin` → research → configure). Don't make up a list.
- If language is empty, use the language the user writes to you in (for example `Japanese`).
- Credentials are not settings. The script reads `XAI_API_KEY` and `SLACK_BOT_TOKEN` from the environment. Never print, echo or log their values. If one is missing, tell the user which variable to set in their shell profile (see the plugin README) and stop.

Every command below starts with the same environment prefix. If a value contains a single quote, write it as `'\''` inside the quotes.

```bash
RESEARCH_X_ACCOUNTS='${user_config.accounts}' \
RESEARCH_X_SLACK_CHANNEL='${user_config.slack_channel}' \
RESEARCH_X_LANGUAGE='<language>' \
RESEARCH_X_TONE='${user_config.tone}' \
RESEARCH_X_TOPIC='${user_config.topic_filter}' \
RESEARCH_X_TIMEZONE='${user_config.timezone}' \
RESEARCH_X_MODEL='${user_config.model}' \
python3 "${CLAUDE_PLUGIN_ROOT}/skills/research-x/scripts/research_x.py" --dry-run
```

## Steps

1. **Dry run first, always.** Run the command above with `--dry-run`. It never posts.
   - stdout has the message texts; stderr has the result JSON (`ok`, `history_read`, `since`, `since_source`, `would_post`, `dropped`, `error`).
   - Show the user how many posts would go out and their URLs, with one or two summaries as a sample.
   - `history_read: false` means the history was not read (no token or no channel). Posting in that state would post again what is already in the channel, so **don't go on to post**.
   - `since_source: first_run` means the history was read but held no research-x post in the last 7 days. That is normal for a first run (it looks back 24 hours).
   - `ok: false`: read `error`, report it, and stop. Nothing was posted.

2. **Post only when the user explicitly asks** (posting sends messages to a channel other people read). Run the same command without `--dry-run`.
   - If the same job also runs on a schedule somewhere, don't run it at the same time: two runs started within minutes of each other can both post the same announcement.
   - `ok: false` after a failed xAI request: nothing was posted, so running again is safe.
   - `ok: false` while posting (Slack error midway): run again with no options. The next run searches the failed run's window again and skips what it already posted by ID.

3. Report the result in one or two lines: how many were posted, their URLs, or why it failed.

## Options

| Option | Meaning |
|---|---|
| `--dry-run` | Fetch and summarize, but don't post |
| `--since-hours H` | Look back H hours instead of from the previous run's start (posted IDs are still skipped) |
| `--model M` | Use this xAI model for this run |
