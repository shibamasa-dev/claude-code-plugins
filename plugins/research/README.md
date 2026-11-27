# research

English | [日本語](README.ja.md)

Skills that read X and the web.

- `research-x` asks xAI's X search about the X accounts you choose, keeps clear update announcements, summarizes each in your language and tone, and posts one Slack message per announcement.
- `read-x-article` reads one X post, long post or X Article from the URL you paste, through the fxtwitter API, and summarizes it. It saves a Markdown copy only when you ask.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install research@shibamasa-plugins
```

For research-x, set `accounts` (and `slack_channel` to post) in the plugin's settings, and put the two credentials in your environment (see Credentials). For read-x-article, set `save_dir` only if you want it to save posts.

## Skills

| Skill | Use it for |
|---|---|
| `research-x` | "Run research-x", "check X for release announcements". Claude always runs a dry run first and shows what would be posted. It posts to Slack only when you ask. The script is `skills/research-x/scripts/research_x.py` (Python, standard library only) |
| `read-x-article` | Paste an x.com or twitter.com status URL and say "read this" or "summarize this". Say "save it" to write a Markdown copy into `save_dir`. Instructions only, no script |

## How research-x works

1. It reads the last 7 days of the channel's history (further back if `--since-hours` asks for it, or if it is retrying a run that searched further back). From research-x's own bot posts it takes where to search from and the X status IDs already posted (from the quoted status URL at the end of each post). Each post's metadata (`event_type: research_x_post`) holds the run's start time, the window it searched and, on its last post, `last: true`. After a run that finished posting, the next one starts at that run's start. After a run that died midway, it searches the same window again, as long as that run's posts are still within the 7-day history read. A retry more than 7 days after the dead run doesn't see it, starts as a first run, and doesn't send the posts that run never sent. With no such post, it looks back 24 hours.
2. It asks xAI about the accounts, 10 per request, with X search required, low reasoning effort and a strict JSON schema.
3. It keeps posts by those accounts made since the start point, using the time encoded in each status ID rather than the model's date, and drops IDs already in the channel.
4. It posts them oldest first, one message each: a separator line, the summary (with Slack control characters escaped, so a summary can't `@here` the channel), and the post URL as a quote.

It keeps no file or database. The channel history is the state, so runs from different machines share it.

**Fail closed.** If any xAI request fails, nothing is posted and the run exits 1, so the next run starts from the same point. A cut connection, a 5xx or an incomplete response is retried once; a 4xx is not.

`--dry-run` never posts. It still reads the history when a token and a channel are set.

## How read-x-article works

1. It takes the handle and status ID from the URL and opens `https://api.fxtwitter.com/<handle>/status/<id>` with WebFetch. It never opens the x.com URL directly, which returns 402.
2. For a regular or long post it reads `tweet.text`. For an X Article it joins `tweet.article.content.blocks[]` (Draft.js blocks) into Markdown; `preview_text` is only the opening.
3. If fxtwitter gives no body, it looks for a copy on tool.lu. If there is none, it reports what it got and stops.
4. It reports the title, author, date and a short summary in your language. That is the end unless you asked it to save.
5. Saving, only on request and only when `save_dir` is set: one file `<YYYYMMDD>_Article_<handle>_<Short_Title>.md` with the source URL, the full text and every image URL. If `save_dir` has an `INDEX.md`, it adds one line in the format that file already uses. It never creates an index and never overwrites a file.

## Configuration

`userConfig` keys, set when you enable the plugin or later with `/plugin`:

| Key | Default | Meaning |
|---|---|---|
| `accounts` | (required) | Comma-separated X handles without `@` |
| `slack_channel` | empty | Slack channel ID to post to and read history from. Required to post |
| `summary_language` | empty | Language of the summaries. Empty means the language you write to Claude in; a run outside Claude uses English |
| `tone` | empty | Tone of the summaries, in free text. Empty means neutral and factual |
| `topic_filter` | empty | Which posts to keep, in free text. Empty means new or changed application features only, no research results, clear update announcements only |
| `timezone` | empty | IANA timezone for times in the prompt and the report. Empty means the system's local timezone |
| `model` | empty | xAI model. Empty means the newest plain `grok-<version>` in the xAI model list, picked on every run |
| `save_dir` | empty | Folder read-x-article saves to when you ask it to. Empty means it never saves |

`accounts` to `model` are research-x's. The skill passes these to the script as environment variables (`RESEARCH_X_ACCOUNTS`, `RESEARCH_X_SLACK_CHANNEL`, `RESEARCH_X_LANGUAGE`, `RESEARCH_X_TONE`, `RESEARCH_X_TOPIC`, `RESEARCH_X_TIMEZONE`, `RESEARCH_X_MODEL`). Set the same variables to run the script without Claude.

### Credentials

The script reads two credentials from the environment. They are not `userConfig` options: a `sensitive` option reaches MCP servers and hooks, but not commands Claude runs through Bash, which is how the skill runs the script.

| Variable | What it is |
|---|---|
| `XAI_API_KEY` | xAI API key. Required, also for `--dry-run` |
| `SLACK_BOT_TOKEN` | Slack bot token with `chat:write` and `channels:history` (`groups:history` for a private channel). The bot must be a member of the channel. Required to post; optional for `--dry-run` (without it the history isn't read) |

Set them in your shell profile, or load them from your password manager there, so that Claude Code inherits them. If one is missing, the script exits 1 with a message naming the variable.

### Scheduling

The plugin doesn't schedule runs. To run daily, call the script from your own scheduler (cron, launchd, systemd timers, CI) with the variables above set. Don't let a scheduled run and a manual run start within minutes of each other: both can read the same history and post the same announcement.

### Where files go

research-x writes no file and keeps no database: the channel history is its state.

read-x-article writes only when you ask it to save, and only into `save_dir`: one Markdown file per post, plus one line in that folder's `INDEX.md` if it has one. These are your own documents, so uninstalling the plugin leaves them in place.

Uninstalling removes nothing.

## Limitations

- Two runs at the same time can post the same announcement twice (there is no lock; the channel history is the only state).
- A post whose URL has no author (`x.com/i/status/<id>`) is dropped, because it can't be confirmed as one of the accounts.
- The summary is the model's. research-x checks the account and the date, not the content.
- The skill puts the settings into the command inside single quotes. A setting that contains `'` (likely only `tone` or `topic_filter`) must be escaped as `'\''`; the skill tells Claude to do that, but a value copied verbatim would break the command.
- read-x-article sends the post URL to fxtwitter (`api.fxtwitter.com`), a third-party service, and, when that fails, searches for it on tool.lu. Both can be down or lack a post, and tool.lu often has no copy of an X Article.
- read-x-article reads through WebFetch, which hands the page to a model. A very long X Article may come back shortened; check the end of the text before relying on a saved copy.
- Not yet verified against the live services, only against recorded and synthetic responses: posting to a real channel, the metadata round trip (`run_started_at`, `since`, `last` written by `chat.postMessage` and read back by `conversations.history` with `include_all_metadata`), and the English prompt against the current xAI model.

### First run

1. `--dry-run` with `XAI_API_KEY` only: the summaries come back in your language and tone, and only from your accounts.
2. Add `SLACK_BOT_TOKEN` and `slack_channel`, `--dry-run` again: `history_read: true`. A `not_in_channel` error means the bot hasn't joined the channel.
3. Post once and note `run_started_at` in that run's JSON output. Then `--dry-run` again: `since` must equal that `run_started_at` exactly. If `since` is instead about 15 minutes before the time of the last post, the metadata did not round-trip, and research-x is dating posts from their timestamps. Then a retry after a run that died midway would treat that run as finished and skip the posts it never sent. Don't schedule runs until `since` matches. (`since_source: slack_history` and `dropped.already_posted` look the same either way, because posted IDs come from the message text.)

## Requirements

- research-x: Python 3.9 or later (standard library only), an xAI API key, and a Slack bot token for posting
- read-x-article: the WebFetch and WebSearch tools in Claude Code. No key

## Tests

```bash
bash plugins/research/tests/run-all.sh
```

Offline: xAI and Slack are replaced by recorded responses under `tests/fixtures/`. They cover research-x; read-x-article is instructions only and has no script to test.
