---
name: get-chrome-history
description: "Reads the Chrome browsing history added since the last run and extracts the user's interests and habits (what they watch on YouTube or Netflix, the tech stacks they read about, hobbies, shopping), structured as input for a user profile or recommendations. It classifies unknown domains and adds them to its knowledge.json, so classification improves with every run. Use it for \"analyze my browser history\", \"what have I been browsing\", \"what am I interested in lately\", or in Japanese 「ブラウザ履歴を分析して」「閲覧傾向を教えて」「最近の興味を把握して」「Chrome 履歴から傾向を抽出して」「閲覧履歴から興味を整理して」."
---

# Chrome history: interests and habits

Reads one Chrome profile's History database, takes only the visits added since the last run, groups them by service and category, and summarizes the user's interests. The services it knows live in `knowledge.json` in the plugin's data directory; Claude adds the domains it classifies there, so each run recognizes more.

Profile = `${user_config.chrome_profile}`. A value that still reads as a `${user_config...}` placeholder, or an empty one, means `Default`; the script treats both that way.

Only read the history when the user asks for it. It is personal data: keep the raw URLs and titles out of anything you write to files or send elsewhere unless the user asks, and summarize instead.

## Step 1: fetch the history

```bash
CLAUDE_PLUGIN_DATA='${CLAUDE_PLUGIN_DATA}' python3 "${CLAUDE_PLUGIN_ROOT}/skills/get-chrome-history/scripts/get_chrome_history.py" --profile '${user_config.chrome_profile}'
```

The script prints one JSON object:

- `entries[]`: every visit kept. A known service has `category` and `service`; anything else has `category: "unknown"`. YouTube entries also have `video_title` (the title without " - YouTube").
- `unknown_domains[]`: the unclassified hosts, aggregated, with `sample_titles`, at most 20 per run (the ones with the most time spent).
- `noise_count`: visits dropped by the thresholds in `filters`, or because their service is marked `"ignore": true`.
- `knowledge_path`: the `knowledge.json` to edit in Step 3.
- `last_fetch_iso`: the start of this window. The first run covers the last 7 days.

If `fetched_count` is 0, tell the user there is no new history and stop.

If it prints `error` (exit 1), the History file was not found for that profile. Show the user `available_profiles` and tell them to set the plugin's `chrome_profile` option to one of them (the directory name, such as `Profile 1`; `chrome://version` shows it at the end of "Profile Path"), then run `/reload-plugins`. An empty list means no Chrome or Chromium profile was found on this machine.

## Step 2: extract per category

Group `entries[]` by `category` and extract:

| category | What to extract |
|---|---|
| `video` | topics and genres from `video_title` or the title |
| `code` | the repository from the URL path (`github.com/<owner>/<repo>`), then languages and technologies |
| `docs` | tech stacks and frameworks from the domain and title |
| `music` | artists and playlists from the title |
| `shopping` | product categories from the title |
| `news` | article topics from the title |
| `social` | handles and topics from the title and URL |

## Step 3: classify unknown domains and update knowledge.json

For each item in `unknown_domains[]`, decide from the host and `sample_titles`:

- What kind of service is it (video, code, docs, music, shopping, news, social, other)?
- Is it useful for understanding the user's interests? If not (login pages, CDNs, redirects), add it with `"ignore": true` (for example `"accounts.example.com": { "category": "other", "label": "Example login", "ignore": true }`). The script then counts its visits as noise instead of showing them.

Add each one to the `services` object of the file at `knowledge_path`, one line per host:

```json
"figma.com": { "category": "design", "label": "Figma" }
```

Prefer the existing categories: `video` / `code` / `docs` / `music` / `shopping` / `news` / `social` / `other`. Add a new one only when it is clearly needed (for example `design`). Then set `last_updated` to the current time (ISO 8601). Edit only that file; the copy shipped with the plugin is only the seed for a first run.

Do not add a domain whose name or titles reveal the user's employer, clients, private tools or local hosts to anything but that local file.

Examples:

| Host | sample_titles | Judgement | category | label |
|---|---|---|---|---|
| figma.com | "Design System – Figma" | design tool | design | Figma |
| notion.so | "My Workspace – Notion" | notes tool | other | Notion |
| leetcode.com | "Two Sum - LeetCode" | coding practice | code | LeetCode |
| booking.com | "Hotels in Lisbon" | travel booking | shopping | Booking.com |

## Step 4: report the tendencies

Reply with this structure, the summary in the user's language:

```json
{
  "period": { "from": "<last_fetch_iso>", "to": "<now, ISO 8601>" },
  "summary": "<one or two sentences on the overall tendency>",
  "tendencies": {
    "video": {
      "services": ["YouTube", "Netflix"],
      "topics": ["AI / machine learning", "programming"],
      "titles": ["An introduction to vector databases"]
    },
    "code": {
      "repos": ["example-org/example-agent"],
      "languages": ["Python", "TypeScript"],
      "topics": ["AI agents", "plugin development"]
    },
    "docs": {
      "services": ["Anthropic Docs", "Stack Overflow"],
      "topics": ["Claude API", "LLM"]
    },
    "music": { "artists": [], "genres": [] },
    "shopping": { "categories": [] },
    "interests": ["design", "travel"]
  },
  "meta": {
    "total_entries": 7,
    "noise_filtered": 1,
    "newly_classified": ["figma.com"],
    "still_unknown": []
  }
}
```

**Leave a field as an empty list when the evidence is thin; don't fill it with guesses.**

The output can feed a user profile or recommendations: `tendencies.video` for video suggestions, `tendencies.code` and `tendencies.docs` for the user's tech stack, `tendencies.interests` and `summary` for interests and hobbies.
