#!/usr/bin/env python3
"""Fetch the Chrome browsing history added since the last run and sort it for Claude.

    get_chrome_history.py [--profile NAME]

Prints one JSON object with three buckets:
  entries          every visit kept; a known service gets `service` and `category`, anything else `category: "unknown"`
  unknown_domains  the unclassified hosts, aggregated (visit count, time spent, up to 3 sample titles), the top 20
                   by time spent, for Claude to classify into knowledge.json
  noise_count      visits dropped by the duration / visit-count thresholds in knowledge.json `filters`, or because
                   their service has `"ignore": true`
plus `knowledge_path` (the file Claude edits to add services) and `last_fetch_iso` (the start of the window).

Profile: --profile names the Chrome profile directory (`Default`, `Profile 1`, ...). Empty, or a `${user_config...}`
placeholder left unsubstituted, means `Default`. The History file is looked up under macOS's
~/Library/Application Support/Google/Chrome/<profile>/ and Linux's ~/.config/google-chrome/<profile>/ and
~/.config/chromium/<profile>/, in that order, on every platform. Chrome locks the file while it runs, so it is copied
to a temporary directory first, read there, and the copy is removed.

State lives in <data>/get-chrome-history/:
  state.json      the newest visit time seen, so the next run fetches only what came after it (the first run fetches
                  the last 7 days). It is written after the output is printed, so a failed run fetches the same
                  window again.
  knowledge.json  the services and filters. The first run copies the seed shipped next to this script; later runs
                  never overwrite it, because Claude adds the services it classifies there.
<data> is $CLAUDE_PLUGIN_DATA when it names this plugin's own directory (`personal-knowledge-<marketplace>` or
`personal-knowledge-inline`), else ~/.claude/state/personal-knowledge: a command run through Bash may carry another
plugin's value, or none. SKILL.md puts the right value in front of the command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PLUGIN = "personal-knowledge"
FEATURE = "get-chrome-history"
SEED_KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge.json"

# Chrome profile roots, tried in this order whatever the platform
CHROME_ROOTS = [
    "~/Library/Application Support/Google/Chrome",
    "~/.config/google-chrome",
    "~/.config/chromium",
]

# How many unknown domains to surface per run (avoids overwhelming Claude on the first run)
MAX_UNKNOWNS_PER_RUN = 20
COLD_START_DAYS = 7
DEFAULT_FILTERS = {"min_visit_duration_seconds": 5, "min_visit_count": 1}
# Chrome stores times as microseconds since 1601-01-01 UTC
EPOCH_DELTA_SECONDS = 11644473600


def plugin_data() -> str | None:
    """$CLAUDE_PLUGIN_DATA when it is this plugin's directory, else None."""
    data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    if not data or data.startswith("${"):
        return None
    name = os.path.basename(os.path.normpath(data))
    return data if name == PLUGIN or name.startswith(PLUGIN + "-") else None


def state_dir() -> Path:
    data = plugin_data()
    if data:
        return Path(data) / FEATURE
    fallback = Path(os.path.expanduser(os.path.join("~", ".claude", "state", PLUGIN, FEATURE)))
    print(f"note: CLAUDE_PLUGIN_DATA is not this plugin's data directory; using {fallback}", file=sys.stderr)
    return fallback


def profile_name(raw: str | None) -> str:
    raw = (raw or "").strip()
    return "Default" if not raw or raw.startswith("${") else raw


def history_candidates(profile: str) -> list[str]:
    return [os.path.join(os.path.expanduser(root), profile, "History") for root in CHROME_ROOTS]


def available_profiles() -> list[str]:
    """Profile directory names that have a History file, under any known root."""
    found = set()
    for root in CHROME_ROOTS:
        root = os.path.expanduser(root)
        if os.path.isdir(root):
            for name in os.listdir(root):
                if os.path.isfile(os.path.join(root, name, "History")):
                    found.add(name)
    return sorted(found)


def read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_knowledge(path: Path) -> dict:
    """Copy the seed to path when there is none yet; never overwrite an existing copy."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SEED_KNOWLEDGE, path)
    return read_json(path)


def lookup_service(host: str, services: dict) -> dict | None:
    """The host itself, then each parent domain down to two labels (www.amazon.co.jp -> amazon.co.jp)."""
    parts = host.split(".")
    for i in range(max(len(parts) - 1, 1)):
        svc = services.get(".".join(parts[i:]))
        if svc:
            return svc
    return None


def to_chrome_time(unix: float) -> int:
    return int((unix + EPOCH_DELTA_SECONDS) * 1_000_000)


def chrome_time_to_iso(chrome_time: int) -> str:
    unix_ts = (chrome_time / 1_000_000) - EPOCH_DELTA_SECONDS
    return datetime.fromtimestamp(unix_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path: Path) -> dict:
    if path.exists():
        return read_json(path)
    # No state yet: fetch the last COLD_START_DAYS days, not the whole history
    chrome_time = to_chrome_time(time.time() - COLD_START_DAYS * 86400)
    return {"last_fetch_chrome_time": chrome_time, "last_fetch_iso": chrome_time_to_iso(chrome_time)}


def save_state(path: Path, chrome_time: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"last_fetch_chrome_time": chrome_time, "last_fetch_iso": chrome_time_to_iso(chrome_time)}, f,
                  indent=2)
    os.replace(tmp, path)


def extract_youtube_title(title: str) -> str:
    return re.sub(r"\s*[-–]\s*YouTube\s*$", "", title).strip()


def fetch_raw(db_path: str, last_fetch_chrome_time: int) -> tuple[list[dict], int]:
    with tempfile.TemporaryDirectory(prefix="chrome-history-") as tmp:
        tmp_db = os.path.join(tmp, "History")
        shutil.copyfile(db_path, tmp_db)
        conn = sqlite3.connect(tmp_db)
        try:
            rows = conn.execute(
                """
                SELECT
                    u.url, u.title, u.visit_count, u.last_visit_time,
                    COALESCE(SUM(v.visit_duration), 0) AS total_duration_us
                FROM urls u
                LEFT JOIN visits v ON v.url = u.id
                WHERE u.hidden = 0 AND u.last_visit_time > ?
                GROUP BY u.id
                ORDER BY u.last_visit_time DESC
                """,
                (last_fetch_chrome_time,),
            ).fetchall()
        finally:
            conn.close()

    max_time = last_fetch_chrome_time
    results = []
    for url, title, visit_count, chrome_time, duration_us in rows:
        results.append({
            "url": url,
            "title": title or "",
            "visit_count": visit_count,
            "total_duration_seconds": round(duration_us / 1_000_000, 1),
            "last_visit_iso": chrome_time_to_iso(chrome_time),
            "_host": urlparse(url).netloc.lower(),
            "_duration_us": duration_us,
        })
        max_time = max(max_time, chrome_time)
    return results, max_time


def classify(raw: list[dict], services: dict, filters: dict) -> tuple[list[dict], dict, int]:
    min_dur_us = filters["min_visit_duration_seconds"] * 1_000_000
    min_count = filters["min_visit_count"]
    entries, unknown_map, noise_count = [], {}, 0
    for e in raw:
        if e["visit_count"] < min_count or e["_duration_us"] < min_dur_us:
            noise_count += 1
            continue
        host = e["_host"]
        entry = {k: e[k] for k in ("url", "title", "visit_count", "total_duration_seconds", "last_visit_iso")}
        svc = lookup_service(host, services)
        if svc and svc.get("ignore"):
            noise_count += 1
            continue
        if svc:
            entry["service"] = svc.get("label", host)
            entry["category"] = svc.get("category", "other")
            if svc["category"] == "video" and "youtube" in host:
                entry["video_title"] = extract_youtube_title(e["title"])
        else:
            agg = unknown_map.setdefault(
                host, {"host": host, "visit_count": 0, "total_duration_seconds": 0.0, "sample_titles": []})
            agg["visit_count"] += e["visit_count"]
            agg["total_duration_seconds"] = round(agg["total_duration_seconds"] + e["total_duration_seconds"], 1)
            if len(agg["sample_titles"]) < 3:
                agg["sample_titles"].append(e["title"])
            entry["category"] = "unknown"
        entries.append(entry)
    return entries, unknown_map, noise_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch new Chrome history and sort it by known service.")
    parser.add_argument("--profile", default="", help="Chrome profile directory name (default: Default)")
    args = parser.parse_args()

    profile = profile_name(args.profile)
    candidates = history_candidates(profile)
    db_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not db_path:
        print(json.dumps({
            "error": f"Chrome History file not found for profile {profile!r}",
            "searched": candidates,
            "available_profiles": available_profiles(),
            "hint": "Set the plugin's chrome_profile option to one of available_profiles",
        }, ensure_ascii=False, indent=2))
        return 1

    sdir = state_dir()
    knowledge_path = sdir / "knowledge.json"
    state_path = sdir / "state.json"
    knowledge = load_knowledge(knowledge_path)
    services = knowledge.get("services", {})
    filters = {**DEFAULT_FILTERS, **knowledge.get("filters", {})}

    state = load_state(state_path)
    last_fetch = state["last_fetch_chrome_time"]
    raw, new_max_time = fetch_raw(db_path, last_fetch)
    entries, unknown_map, noise_count = classify(raw, services, filters)

    unknown_domains = sorted(unknown_map.values(), key=lambda x: x["total_duration_seconds"],
                             reverse=True)[:MAX_UNKNOWNS_PER_RUN]
    out = json.dumps({
        "db_path": db_path,
        "profile": profile,
        "knowledge_path": str(knowledge_path),
        "last_fetch_iso": state.get("last_fetch_iso"),
        "fetched_count": len(entries),
        "noise_count": noise_count,
        "unknown_domain_count": len(unknown_map),
        "unknown_domains": unknown_domains,
        "entries": entries,
    }, ensure_ascii=False, indent=2)
    # Write UTF-8 whatever the locale, and only then move the cursor, so a failed print loses no window
    sys.stdout.buffer.write(out.encode("utf-8") + b"\n")
    sys.stdout.flush()
    if new_max_time > last_fetch:
        save_state(state_path, new_max_time)
    return 0


if __name__ == "__main__":
    sys.exit(main())
