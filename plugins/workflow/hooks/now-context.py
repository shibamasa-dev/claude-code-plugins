#!/usr/bin/env python3
"""now-context: a UserPromptSubmit hook that adds the current date and time as one line, every turn.

The session context carries the date but not the time, so anything that depends on the hour (quiet hours, how long
ago something happened, whether it is morning or night) goes wrong when Claude forgets to run `date`.

Output (stdout, added to the context):  [now] 2026-11-24 (Tue) 14:05 JST
The time zone is userConfig `timezone` (CLAUDE_PLUGIN_OPTION_TIMEZONE, an IANA name such as Asia/Tokyo or UTC).
Empty means the system time zone. A name that does not resolve falls back to the system time zone and says so on
stderr. The day name is English whatever the locale. Always exits 0, and prints nothing rather than fail.
"""
import os
import sys
from datetime import datetime


def now_line(tz_name):
    tz = None
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
        except Exception:  # unknown name, or no tz database: use the system time zone
            print(f"now-context: unknown time zone {tz_name!r}; using the system time zone", file=sys.stderr)
    t = datetime.now(tz) if tz else datetime.now().astimezone()
    day = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[t.weekday()]  # not %a: that follows the locale
    return f"[now] {t:%Y-%m-%d} ({day}) {t:%H:%M} {t.tzname() or t.strftime('%z')}"


def main():
    try:
        print(now_line(os.environ.get("CLAUDE_PLUGIN_OPTION_TIMEZONE", "").strip()))
    except Exception as e:  # never stop the prompt
        print(f"now-context: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
    sys.exit(0)
