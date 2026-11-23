#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""stdio MCP server for the creative plugin's image history.

Its whole job: run SQL, apply the schema migrations, and provide img_norm(text) on SQLite.
Claude writes the SQL; the rules that must hold on every write live in the schema (migrations/).

Where the data lives comes from the environment, which .mcp.json fills from userConfig:
    CREATIVE_HISTORY_ROUTE         the saved store: 'sqlite', 'postgres' or 'connector' (refuse every call: the data
                                   lives behind a connector); empty until Claude saves it on first use
    CREATIVE_HISTORY_DATABASE_URL  postgresql://... -> Postgres
    CREATIVE_HISTORY_SQLITE_PATH   SQLite file; empty -> $CLAUDE_PLUGIN_DATA/image-history/history.sqlite3
The database is opened, and pending migrations applied, on the first tool call, never before
`initialize` is answered: a host that doesn't respond must not stall the MCP handshake.
A connection failure is reported as a tool error, with the database_url and its password redacted. The server
never falls back to another store, which would split the data across two places: when the saved route's setting is
missing (route=postgres without database_url) every call fails instead.

Standard library only. psycopg, which only Postgres needs, is added at start by re-running the script through
`uv run --with` when database_url is in use and psycopg is missing, so a SQLite user downloads nothing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

SERVER_NAME = "creative-history"
SERVER_VERSION = "0.1.0"
MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
MAX_ROWS = 500
CONNECT_TIMEOUT_S = 10
PSYCOPG = "psycopg[binary]>=3.1"
ROUTES = ("sqlite", "postgres", "connector")

TOOLS = [
    {
        "name": "execute_sql",
        "description": (
            "Run one SQL statement against the image history database and return its rows as JSON. "
            "Tables: img_attempts, img_references, img_schema_migrations; view: img_v_attempts. "
            "img_norm(text) (NFKC + lower case) is available on both SQLite and Postgres. "
            "Write SQL that runs on both: string literals with ' doubled, no bind parameters. "
            f"At most {MAX_ROWS} rows are returned."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "One SQL statement"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "apply_migrations",
        "description": (
            "Apply pending schema migrations (they also run on the first tool call) and report the backend "
            "(sqlite or postgres), where the SQLite file is, and the applied schema versions. "
            "Call it first to check that the server reaches its store; save backend as the route."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def norm(s):
    """The same normalization as the Postgres img_norm(): NFKC, then lower case."""
    return None if s is None else unicodedata.normalize("NFKC", s).lower()


def setting(name: str) -> str:
    """A userConfig value from the environment. An unset option may arrive as the literal ${user_config.X}."""
    v = os.environ.get(name, "").strip()
    return "" if v.startswith("${") else v


class SQLite:
    dialect = "sqlite"

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.where = str(path)
        self.conn = sqlite3.connect(str(path), isolation_level=None, timeout=10)  # autocommit; scripts BEGIN themselves
        self.conn.create_function("img_norm", 1, norm, deterministic=True)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def query(self, sql: str):
        cur = self.conn.execute(sql)
        return cur.description, cur

    def run_script(self, sql: str):
        # One transaction per migration file, which is why the files must not contain BEGIN or COMMIT
        try:
            self.conn.executescript("BEGIN IMMEDIATE;\n" + sql + "\nCOMMIT;")
        except BaseException:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise


class Postgres:
    dialect = "postgres"

    def __init__(self, url: str):
        try:
            import psycopg  # only Postgres users need the dependency loaded
        except ImportError:
            raise RuntimeError(f"database_url is set but psycopg is missing: install uv, or {PSYCOPG} for this python3")

        self.psycopg = psycopg
        self.url = url
        self.where = "database_url"
        self.conn = self.connect()

    def connect(self):
        return self.psycopg.connect(self.url, autocommit=True, connect_timeout=CONNECT_TIMEOUT_S)

    def lost(self) -> bool:
        return self.conn.closed or self.conn.broken

    def query(self, sql: str):
        """Run one statement. A connection already known to be lost is replaced before anything is sent.
        If the connection drops while the statement runs (database restart, idle timeout, a network blip),
        the statement is not run again: with autocommit it may already be committed, and a second run
        would apply a write twice. The connection is replaced for the next call and the call fails.
        Other errors, such as a syntax error, are raised as they are."""
        if self.lost():
            self.conn = self.connect()
        try:
            cur = self.conn.execute(sql)
        except self.psycopg.OperationalError as e:
            if not self.lost():
                raise
            try:
                self.conn = self.connect()
            except self.psycopg.OperationalError:
                pass  # the next call tries again
            raise ConnectionError(
                "the database connection dropped while this statement ran, so it may or may not have been "
                "applied. Check the current state with a SELECT before running it again. "
                f"({type(e).__name__}: {e})"
            ) from e
        return cur.description, cur

    def run_script(self, sql: str):
        # One transaction per migration file, which is why the files must not contain BEGIN or COMMIT
        if self.lost():
            self.conn = self.connect()
        with self.conn.transaction():
            # Two servers starting at once must not both create the schema
            self.conn.execute("SELECT pg_advisory_xact_lock(hashtext('img_schema_migrations'))")
            self.conn.execute(sql)


def open_backend():
    route = setting("CREATIVE_HISTORY_ROUTE")
    url = setting("CREATIVE_HISTORY_DATABASE_URL")
    if route and route not in ROUTES:
        raise RuntimeError(f"route is {route!r}, which is none of {', '.join(ROUTES)}. Stop and ask the user where "
                           "the image history lives; the server opens no store until route names one.")
    if route == "connector":
        raise RuntimeError(
            "route is 'connector': this image history lives behind a claude.ai connector, so use the connector's SQL tool. "
            "Change the route only if the user asks to move the data."
        )
    if route == "postgres" and not url:
        raise RuntimeError("route is 'postgres' but database_url is not set. Stop and tell the user: the history lives "
                           "in Postgres, and the server never opens SQLite in its place. Ask them to set database_url again.")
    if route == "sqlite" and url:
        raise RuntimeError("route is 'sqlite' but database_url is set. Stop and ask the user which store holds the "
                           "history; the server opens neither until the two settings agree.")
    if url:  # route=postgres, or no route saved yet
        return Postgres(url)
    p = setting("CREATIVE_HISTORY_SQLITE_PATH")
    data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    if p:
        path = Path(p).expanduser()
        if not path.is_absolute():
            if not data:
                raise RuntimeError(f"sqlite_path {p!r} is relative but CLAUDE_PLUGIN_DATA is not set")
            path = Path(data) / path
    elif data:
        path = Path(data) / "image-history" / "history.sqlite3"
    else:
        raise RuntimeError("no database: set sqlite_path or database_url (CLAUDE_PLUGIN_DATA is not set either)")
    return SQLite(path)


def applied_versions(db) -> list:
    try:
        _, cur = db.query("SELECT version FROM img_schema_migrations ORDER BY version")
        return [r[0] for r in cur.fetchall()]
    except Exception:  # the table doesn't exist before the first migration
        if db.dialect == "postgres" and not db.conn.autocommit:
            db.conn.rollback()
        return []


def migrate(db) -> list:
    done = set(applied_versions(db))
    applied = []
    for f in sorted((MIGRATIONS / db.dialect).glob("*.sql")):
        if f.stem in done:
            continue
        db.run_script(f.read_text(encoding="utf-8"))  # each file records its own version
        applied.append(f.stem)
    return applied


class State:
    db = None
    applied_on_open: list = []


def get_db():
    """Open and migrate on first use; retried on every call until it works (never falls back)."""
    if State.db is None:
        db = open_backend()
        State.applied_on_open = migrate(db)
        State.db = db
    return State.db


def jsonable(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    return str(v)  # Decimal, datetime and the like


def tool_execute_sql(args: dict) -> dict:
    sql = args.get("query")
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("query must be a non-empty SQL string")
    db = get_db()
    desc, cur = db.query(sql)
    if not desc:
        return {"rowcount": cur.rowcount}
    rows = cur.fetchmany(MAX_ROWS + 1)
    out = {
        "columns": [d[0] for d in desc],
        "rows": [[jsonable(v) for v in r] for r in rows[:MAX_ROWS]],
    }
    if len(rows) > MAX_ROWS:
        out["truncated"] = True
    return out


def tool_apply_migrations(_args: dict) -> dict:
    db = get_db()
    now = migrate(db)
    return {
        "backend": db.dialect,
        "database": db.where,
        "applied_on_open": State.applied_on_open,
        "applied_now": now,
        "schema_versions": applied_versions(db),
    }


def redact(text: str) -> str:
    """Keep database_url and its password out of an error message. psycopg's errors quote parts of the connection
    string (a malformed one comes back nearly whole), so the URL, its password (decoded too) and every word of the
    message that is a piece of the URL are replaced."""
    url = setting("CREATIVE_HISTORY_DATABASE_URL")
    if not url:
        return text
    found = [url]
    m = re.search(r"[^/@:\s]*:([^@\s/]*)@", url)  # [scheme://]user:password@host
    if m:
        found.append(m.group(1))
    m = re.search(r"(?:^|\s)password\s*=\s*('(?:[^'\\]|\\.)*'|\S+)", url)  # host=... password=...
    if m:
        found.append(m.group(1).strip("'"))
    found += [unquote(f) for f in found]
    for f in sorted({f for f in found if len(f) >= 4}, key=len, reverse=True):
        text = text.replace(f, "[redacted]")
    for word in set(re.split(r"[\s\"'(),]+", text)):
        if len(word) >= 4 and word in url:
            text = text.replace(word, "[redacted]")
    return text


HANDLERS = {"execute_sql": tool_execute_sql, "apply_migrations": tool_apply_migrations}


def handle(msg: dict):
    method = msg.get("method")
    if method == "initialize":
        return {
            "protocolVersion": (msg.get("params") or {}).get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = msg.get("params") or {}
        fn = HANDLERS.get(params.get("name"))
        if fn is None:
            raise LookupError(f"unknown tool: {params.get('name')}")
        try:
            result = fn(params.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
        except Exception as e:  # SQL and connection errors go back to Claude as tool errors
            return {"content": [{"type": "text", "text": redact(f"{type(e).__name__}: {e}")}], "isError": True}
    raise LookupError(f"method not found: {method}")


def send(obj: dict):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def ensure_psycopg():
    """Only Postgres needs psycopg: when database_url is in use and psycopg is missing, run this script again
    through uv with it added. Without uv the first tool call reports the missing package instead."""
    route = setting("CREATIVE_HISTORY_ROUTE")
    if not setting("CREATIVE_HISTORY_DATABASE_URL") or route not in ("", "postgres"):
        return
    if os.environ.get("CREATIVE_HISTORY_WITH_PSYCOPG"):
        return  # already re-run once
    try:
        import psycopg  # noqa: F401
        return
    except ImportError:
        pass
    uv = shutil.which("uv")
    if uv:
        os.environ["CREATIVE_HISTORY_WITH_PSYCOPG"] = "1"
        os.execv(uv, [uv, "run", "--quiet", "--with", PSYCOPG, "--script", os.path.abspath(__file__)])


def main():
    ensure_psycopg()
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        try:
            msg = json.loads(line.decode("utf-8"))
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        if "id" not in msg:  # notifications (notifications/initialized, cancelled) need no answer
            continue
        try:
            send({"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)})
        except LookupError as e:
            send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": str(e)}})


if __name__ == "__main__":
    main()
