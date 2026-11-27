# -*- coding: utf-8 -*-
"""Cases for get_chrome_history.py, one behaviour per verdict row.

Every case gets a fresh temp root holding HOME, TMPDIR and a plugin data directory named like Claude Code names it
(`personal-knowledge-<marketplace>`), so nothing touches the real home or a real Chrome profile. The fixture History has
the subset of Chrome's schema the script reads (`urls`, `visits`) with fictional URLs. Expected values come from the
skill text (SKILL.md: three buckets, 7-day first window, seed copied once, data directory) and the fixture rows below,
not from the script's output.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "skills", "get-chrome-history")
SCRIPT = os.path.join(SKILL, "scripts", "get_chrome_history.py")
SEED = os.path.join(SKILL, "knowledge.json")
MAC_ROOT = os.path.join("Library", "Application Support", "Google", "Chrome")
LINUX_ROOT = os.path.join(".config", "google-chrome")
DATA_NAME = "personal-knowledge-test-marketplace"
HOUR = 3600

# (url, title, visit_count, hours ago, seconds spent, hidden)
ROWS = [
    ("https://www.youtube.com/watch?v=abc123", "Learning SQLite in 10 minutes - YouTube", 2, 1, 120, 0),
    ("https://github.com/example-org/example-repo", "example-org/example-repo", 1, 2, 60, 0),
    ("https://blog.example.com/post/1", "日本語の記事 - Example Blog", 1, 3, 30, 0),
    ("https://blog.example.com/post/2", "Second post - Example Blog", 1, 3, 20, 0),
    ("https://www.example.org/bounce", "Quick bounce", 1, 1, 1, 0),
    ("https://old.example.net/", "Old page", 1, 24 * 10, 100, 0),
    ("https://hidden.example.net/", "Hidden page", 1, 1, 60, 1),
    ("https://www.amazon.co.jp/dp/0000000000", "A book", 1, 1, 30, 0),
    ("https://accounts.example.com/login", "Sign in", 1, 1, 30, 0),
]


def chrome_time(unix):
    return int((unix + 11644473600) * 1_000_000)


def add_rows(db, rows, now):
    conn = sqlite3.connect(db)
    for url, title, count, hours_ago, spent, hidden in rows:
        t = chrome_time(now - hours_ago * HOUR)
        cur = conn.execute(
            "INSERT INTO urls (url, title, visit_count, typed_count, last_visit_time, hidden) VALUES (?, ?, ?, 0, ?, ?)",
            (url, title, count, t, hidden))
        conn.execute("INSERT INTO visits (url, visit_time, from_visit, transition, visit_duration) VALUES (?, ?, 0, 0, ?)",
                     (cur.lastrowid, t, spent * 1_000_000))
    conn.commit()
    conn.close()


def make_history(home, root=MAC_ROOT, profile="Default", rows=ROWS, now=None):
    d = os.path.join(home, root, profile)
    os.makedirs(d, exist_ok=True)
    db = os.path.join(d, "History")
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE urls (id INTEGER PRIMARY KEY AUTOINCREMENT, url LONGVARCHAR, title LONGVARCHAR,
            visit_count INTEGER DEFAULT 0 NOT NULL, typed_count INTEGER DEFAULT 0 NOT NULL,
            last_visit_time INTEGER NOT NULL, hidden INTEGER DEFAULT 0 NOT NULL);
        CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER NOT NULL, visit_time INTEGER NOT NULL,
            from_visit INTEGER, transition INTEGER DEFAULT 0 NOT NULL, visit_duration INTEGER DEFAULT 0 NOT NULL);
    """)
    conn.close()
    add_rows(db, rows, now or time.time())
    return db


class Env:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="gch-test-")
        self.home = os.path.join(self.root, "home")
        self.tmp = os.path.join(self.root, "tmp")
        self.data = os.path.join(self.root, "plugins-data", DATA_NAME)
        os.makedirs(self.home)
        os.makedirs(self.tmp)

    @property
    def state_dir(self):
        return os.path.join(self.data, "get-chrome-history")

    @property
    def fallback_dir(self):
        return os.path.join(self.home, ".claude", "state", "personal-knowledge", "get-chrome-history")

    def env(self, data=None, **extra):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("LC_", "LANG", "PYTHON", "CLAUDE_"))}
        env.update(HOME=self.home, TMPDIR=self.tmp, CLAUDE_PLUGIN_DATA=self.data if data is None else data, **extra)
        return env

    def run(self, *args, data=None, **extra):
        # -B: the stock macOS python3 caches stdlib bytecode under ~/Library/Caches/com.apple.python, which is the
        # interpreter's doing, not the script's, and would hide what the script writes
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], env=self.env(data, **extra), capture_output=True)
        try:
            out = json.loads(p.stdout.decode("utf-8"))
        except ValueError:
            out = None
        return p.returncode, out, p.stderr.decode("utf-8", "replace")

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def files_under(root):
    found = set()
    for d, _, names in os.walk(root):
        for n in names:
            found.add(os.path.relpath(os.path.join(d, n), root))
    return found


def tree_state(root):
    """path -> (size, mtime) of every file, to tell whether a directory changed."""
    return {f: (os.path.getsize(os.path.join(root, f)), os.path.getmtime(os.path.join(root, f)))
            for f in files_under(root)}


def by_url(out, url):
    return next((e for e in out["entries"] if e["url"] == url), None)


# Each case returns (got, want); the row is ok when they are equal
def case_known_service():
    e = Env()
    try:
        make_history(e.home)
        rc, out, _ = e.run()
        y = by_url(out, ROWS[0][0])
        return (rc, y and y.get("service"), y and y.get("category")), (0, "YouTube", "video")
    finally:
        e.close()


def case_youtube_title():
    e = Env()
    try:
        make_history(e.home)
        _, out, _ = e.run()
        return by_url(out, ROWS[0][0]).get("video_title"), "Learning SQLite in 10 minutes"
    finally:
        e.close()


def case_parent_domain():
    e = Env()
    try:
        make_history(e.home)
        _, out, _ = e.run()
        a = by_url(out, ROWS[7][0])
        return (a.get("service"), a.get("category")), ("Amazon JP", "shopping")
    finally:
        e.close()


def case_unknown_bucket():
    e = Env()
    try:
        make_history(e.home)
        _, out, _ = e.run()
        blog = next((u for u in out["unknown_domains"] if u["host"] == "blog.example.com"), {})
        cats = {by_url(out, ROWS[2][0])["category"], by_url(out, ROWS[3][0])["category"]}
        return ((blog.get("visit_count"), blog.get("total_duration_seconds"), len(blog.get("sample_titles", [])), cats),
                (2, 50.0, 2, {"unknown"}))
    finally:
        e.close()


def case_noise_bucket():
    e = Env()
    try:
        make_history(e.home)
        _, out, _ = e.run()
        return (out["noise_count"], by_url(out, ROWS[4][0])), (1, None)
    finally:
        e.close()


def case_first_run_window():
    e = Env()
    try:
        make_history(e.home)
        _, out, _ = e.run()
        return by_url(out, ROWS[5][0]), None  # 10 days old: outside the 7-day first window
    finally:
        e.close()


def case_hidden_skipped():
    e = Env()
    try:
        make_history(e.home)
        _, out, _ = e.run()
        return by_url(out, ROWS[6][0]), None
    finally:
        e.close()


def case_incremental():
    e = Env()
    try:
        db = make_history(e.home)
        e.run()
        _, second, _ = e.run()
        add_rows(db, [("https://news.example.com/today", "Today", 1, 0, 40, 0)], time.time())
        _, third, _ = e.run()
        return ((second["fetched_count"], [x["url"] for x in third["entries"]]),
                (0, ["https://news.example.com/today"]))
    finally:
        e.close()


def case_profiles_keep_own_cursor():
    e = Env()
    try:
        make_history(e.home, rows=[("https://a.example.com/", "A", 1, 1, 30, 0)])
        make_history(e.home, profile="Profile 1", rows=[("https://b.example.com/", "B", 1, 2, 30, 0)])
        e.run()  # Default: its cursor moves to 1 hour ago
        _, out, _ = e.run("--profile", "Profile 1")  # first run of Profile 1: its 2-hour-old visit is new to it
        return [x["url"] for x in out["entries"]], ["https://b.example.com/"]
    finally:
        e.close()


def case_state_cursor():
    e = Env()
    try:
        now = time.time()
        db = make_history(e.home, now=now)
        e.run()
        with open(os.path.join(e.state_dir, "state.json"), encoding="utf-8") as f:
            state = json.load(f)
        newest = chrome_time(now - 1 * HOUR)  # the newest non-hidden rows are 1 hour old
        return state["cursors"][db]["last_fetch_chrome_time"], newest
    finally:
        e.close()


def case_writes_only_data_dir():
    e = Env()
    try:
        make_history(e.home)
        before = files_under(e.root)
        skill_before = tree_state(SKILL)
        rc, _, _ = e.run()
        new = files_under(e.root) - before
        want = {os.path.relpath(os.path.join(e.state_dir, n), e.root) for n in ("knowledge.json", "state.json")}
        return (rc, new, tree_state(SKILL) == skill_before, os.listdir(e.tmp)), (0, want, True, [])
    finally:
        e.close()


def case_seed_copied():
    e = Env()
    try:
        make_history(e.home)
        e.run()
        with open(SEED, "rb") as a, open(os.path.join(e.state_dir, "knowledge.json"), "rb") as b:
            return a.read() == b.read(), True
    finally:
        e.close()


def case_seed_not_overwritten():
    e = Env()
    try:
        make_history(e.home)
        e.run()
        path = os.path.join(e.state_dir, "knowledge.json")
        with open(path, encoding="utf-8") as f:
            k = json.load(f)
        k["services"]["blog.example.com"] = {"category": "docs", "label": "Example Blog"}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(k, f)
        os.remove(os.path.join(e.state_dir, "state.json"))  # fetch the same window again
        _, out, _ = e.run()
        with open(path, encoding="utf-8") as f:
            kept = "blog.example.com" in json.load(f)["services"]
        return (kept, by_url(out, ROWS[2][0]).get("service")), (True, "Example Blog")
    finally:
        e.close()


def case_ignored_service():
    e = Env()
    try:
        make_history(e.home)
        os.makedirs(e.state_dir)
        with open(SEED, encoding="utf-8") as f:
            k = json.load(f)
        k["services"]["accounts.example.com"] = {"category": "other", "label": "Example login", "ignore": True}
        with open(os.path.join(e.state_dir, "knowledge.json"), "w", encoding="utf-8") as f:
            json.dump(k, f)
        _, out, _ = e.run()
        return (by_url(out, ROWS[8][0]), out["noise_count"]), (None, 2)
    finally:
        e.close()


def case_foreign_data_dir():
    e = Env()
    try:
        make_history(e.home)
        foreign = os.path.join(e.root, "plugins-data", "workflow-test-marketplace")
        rc, _, _ = e.run(data=foreign)
        return ((rc, os.path.exists(foreign), sorted(files_under(e.fallback_dir))),
                (0, False, ["knowledge.json", "state.json"]))
    finally:
        e.close()


def case_placeholder_data_dir():
    e = Env()
    try:
        make_history(e.home)
        rc, _, _ = e.run(data="${CLAUDE_PLUGIN_DATA}")
        return (rc, sorted(files_under(e.fallback_dir))), (0, ["knowledge.json", "state.json"])
    finally:
        e.close()


def case_missing_profile():
    e = Env()
    try:
        make_history(e.home)
        rc, out, _ = e.run("--profile", "Profile 9")
        return ((rc, "error" in (out or {}), (out or {}).get("available_profiles"), os.path.exists(e.data)),
                (1, True, ["Default"], False))
    finally:
        e.close()


def case_placeholder_profile():
    e = Env()
    try:
        make_history(e.home)
        rc, out, _ = e.run("--profile", "${user_config.chrome_profile}")
        return (rc, out and out.get("profile")), (0, "Default")
    finally:
        e.close()


def case_linux_profile_path():
    e = Env()
    try:
        db = make_history(e.home, root=LINUX_ROOT, profile="Profile 1")
        rc, out, _ = e.run("--profile", "Profile 1")
        return (rc, out and out.get("db_path")), (0, db)
    finally:
        e.close()


ASCII = {"LC_ALL": "C", "PYTHONIOENCODING": "ascii"}


def case_ascii_locale():
    e = Env()
    try:
        make_history(e.home)
        rc, out, _ = e.run(**ASCII)
        return (rc, (by_url(out or {"entries": []}, ROWS[2][0]) or {}).get("title")), (0, ROWS[2][1])
    finally:
        e.close()


def case_ascii_locale_error():
    e = Env()
    try:
        make_history(e.home)
        rc, out, _ = e.run("--profile", "仕事用", **ASCII)
        return (rc, (out or {}).get("profile")), (1, "仕事用")
    finally:
        e.close()


def case_failed_output_keeps_window():
    e = Env()
    try:
        make_history(e.home)
        r, w = os.pipe()
        os.close(r)  # nobody reads: the script's write fails
        p = subprocess.run([sys.executable, "-B", SCRIPT], env=e.env(), stdout=w, stderr=subprocess.DEVNULL)
        os.close(w)
        return (p.returncode != 0, os.path.exists(os.path.join(e.state_dir, "state.json"))), (True, False)
    finally:
        e.close()


def case_title_cleaned():
    e = Env()
    try:
        url = "https://shout.example.com/"
        make_history(e.home, rows=[(url, "\x1b[31mRed\u202e\n" + "x" * 500, 1, 1, 30, 0)])
        _, out, _ = e.run()
        t = by_url(out, url)["title"]
        return (len(t) <= 200, t.startswith("[31mRed"), any(ord(c) < 32 or 0x202a <= ord(c) <= 0x202e for c in t)), (True, True, False)
    finally:
        e.close()


CASES = [
    ("known service gets service and category", case_known_service),
    ("YouTube entry gets video_title", case_youtube_title),
    ("www.amazon.co.jp matches amazon.co.jp", case_parent_domain),
    ("unknown hosts aggregated in unknown_domains", case_unknown_bucket),
    ("short visit counted as noise, not listed", case_noise_bucket),
    ("first run skips visits older than 7 days", case_first_run_window),
    ("hidden urls skipped", case_hidden_skipped),
    ("second run fetches only new visits", case_incremental),
    ("state.json holds the newest visit time", case_state_cursor),
    ("each profile keeps its own cursor", case_profiles_keep_own_cursor),
    ("fresh run writes only knowledge.json and state.json under the data dir", case_writes_only_data_dir),
    ("first run copies the seed knowledge.json", case_seed_copied),
    ("user's knowledge.json is never overwritten", case_seed_not_overwritten),
    ("service with ignore:true counted as noise", case_ignored_service),
    ("another plugin's CLAUDE_PLUGIN_DATA falls back to ~/.claude/state", case_foreign_data_dir),
    ("unsubstituted ${CLAUDE_PLUGIN_DATA} falls back to ~/.claude/state", case_placeholder_data_dir),
    ("missing profile exits 1 with the profiles found, writes nothing", case_missing_profile),
    ("unsubstituted ${user_config...} profile means Default", case_placeholder_profile),
    ("Linux ~/.config/google-chrome profile is found", case_linux_profile_path),
    ("non-ASCII titles print under an ASCII locale", case_ascii_locale),
    ("missing-profile error prints under an ASCII locale", case_ascii_locale_error),
    ("output that cannot be written leaves state.json unwritten", case_failed_output_keeps_window),
    ("titles lose control characters and are cut at 200", case_title_cleaned),
]


def main():
    bad = 0
    for name, fn in CASES:
        try:
            got, want = fn()
        except Exception as exc:  # a crashing case is a mismatch, not a crashed run
            got, want = "crashed: %r" % exc, "ok"
        if got == want:
            print("  %s -> ok (expect ok)" % name)
        else:
            bad += 1
            print("  %s [got: %r, want: %r] -> bad (expect ok)" % (name, got, want))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
