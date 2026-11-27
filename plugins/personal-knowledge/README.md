# personal-knowledge

English | [日本語](README.ja.md)

Skills that keep a personal local data store on your machine. Currently one skill, `get-chrome-history`, which reads your Chrome browsing history and summarizes your interests, learning a little more about the sites you use on every run.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install personal-knowledge@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `get-chrome-history` | "Analyze my browser history", "what have I been browsing lately", "what am I interested in". Claude reads the visits added since the last run, groups them by service (video, code, docs, music, shopping, news, social), classifies the domains it doesn't know yet, and reports your tendencies as JSON that can feed a user profile or recommendations. The script is `skills/get-chrome-history/scripts/get_chrome_history.py` (Python, standard library only) |

## How get-chrome-history works

1. **Read.** The script finds the History database of the profile in `chrome_profile`, under `~/Library/Application Support/Google/Chrome/<profile>/` (macOS), `~/.config/google-chrome/<profile>/` or `~/.config/chromium/<profile>/` (Linux). Chrome locks the file while it runs, so the script copies it to a temporary directory, reads the copy and removes it. It never writes to Chrome's files.
2. **Window.** It takes the visits after the newest one it saw last time. The first run takes the last 7 days.
3. **Sort.** Each visit lands in one of three buckets: a known service from `knowledge.json` (with its category), an unknown domain (aggregated, with sample titles, the top 20 by time spent), or noise (shorter than `min_visit_duration_seconds`, fewer visits than `min_visit_count`, or a service marked `"ignore": true`).
4. **Learn.** Claude classifies the unknown domains and adds them to your `knowledge.json`, so the next run recognizes them.
5. **Report.** Claude summarizes the tendencies per category in your language and leaves a field empty when the evidence is thin.

Page titles are written by the sites you visit, so the script drops control characters and cuts them at 200 characters, and the skill tells Claude never to follow an instruction found in a title or URL. Your history stays on your machine: the script prints to Claude's session only, and the skill tells Claude to summarize rather than copy raw URLs and titles elsewhere.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `chrome_profile` | `Default` | The Chrome profile directory to read (`Default`, `Profile 1`, ...). Empty means `Default`. When the profile has no History file, the skill lists the profiles it did find |

To find a profile's directory name, open `chrome://version` in that profile and look at "Profile Path".

### Where files go

| File | Place | What it is |
|---|---|---|
| `knowledge.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | The services and filters the skill knows. The first run copies the seed shipped in `skills/get-chrome-history/knowledge.json`; after that Claude adds to your copy and updates never overwrite it |
| `state.json` | `${CLAUDE_PLUGIN_DATA}/get-chrome-history/` | The newest visit time seen. Delete it to fetch the last 7 days again |
| The History copy | the system temp directory | Removed as soon as it has been read |

`${CLAUDE_PLUGIN_DATA}` is `~/.claude/plugins/data/personal-knowledge-<marketplace>/`. When the script runs without it (for example by hand from a terminal), it uses `~/.claude/state/personal-knowledge/get-chrome-history/` instead and says so on stderr.

Uninstalling the plugin from the last place it is installed deletes `${CLAUDE_PLUGIN_DATA}`, and with it your `knowledge.json` and `state.json`, unless you pass `--keep-data`. The fallback directory under `~/.claude/state/` is not touched.

## Limitations

- Chrome and Chromium on macOS and Linux only. Windows, other Chromium-based browsers (Edge, Brave, Arc) and Firefox are not read.
- One profile per run.
- A service matches by host and its parent domains (`www.amazon.co.jp` matches `amazon.co.jp`), not by path, so two services on one host can't be told apart.
- The window is by each URL's last visit time, and a URL's `visit_count` and time spent are its totals in Chrome, not just within the window.
- The copy is taken while Chrome may be writing. A visit Chrome had not committed yet when the copy was taken is missed if a newer visit was already in the copy.

## Requirements

- Google Chrome or Chromium
- macOS or Linux
- Python 3.9 or later (standard library only)

## Tests

```bash
bash plugins/personal-knowledge/tests/run-all.sh
```

Offline: every case builds a History database with Chrome's `urls` / `visits` tables and fictional URLs in a temp directory, and points `HOME`, `TMPDIR` and `CLAUDE_PLUGIN_DATA` there, so no real profile or home directory is read or written. The rows check the three buckets, the 7-day first window, the incremental fetch, that a fresh run writes only `knowledge.json` and `state.json` under the data directory (and nothing in the skill directory), that the seed is copied once and never overwritten, the fallback directory, a missing profile, the Linux profile path, output (and the missing-profile error) under an ASCII locale, that a run whose output can't be written leaves `state.json` unwritten, and title cleaning.
