#!/usr/bin/env python3
"""CLI that drives the Spotify Web API for Claude (standard library only, Python 3.9+).

Auth is Authorization Code + PKCE (no client secret). The client ID and tokens (client_id / refresh_token /
access_token / expires_at) live in one token store, picked by SPOTIFY_TOKEN_STORE:
  file (default) -- one JSON file, $CLAUDE_PLUGIN_DATA/spotify/token.json, mode 0600 in a 0700 directory
  1password      -- one 1Password item through the op CLI and a service account (SPOTIFY_OP_ITEM, SPOTIFY_OP_VAULT,
                    SPOTIFY_OP_TOKEN_ENV), so no command waits for Touch ID or a password
An empty value, or one still reading as an unsubstituted ${...} placeholder, counts as unset.

Output is JSON on stdout (ensure_ascii=False). Tokens are never printed.
Errors are one JSON line on stderr {"error": ..., "status": ..., "reason": ...} with exit code
1 (API error) / 2 (bad argument or precondition) / 3 (auth missing, expired, or the store is unusable).

Settings (the skill passes them, because commands run through Bash get no plugin variables):
  CLAUDE_PLUGIN_DATA        the plugin's data directory (file store)
  SPOTIFY_TOKEN_STORE       file | 1password
  SPOTIFY_OP_ITEM           1Password item title or ID (default "Spotify Web API")
  SPOTIFY_OP_VAULT          1Password vault name or ID (required with 1password)
  SPOTIFY_OP_TOKEN_ENV      NAME of the environment variable holding the service account token (required with
                            1password). Its value goes only into the env of the op subprocess, as OP_SERVICE_ACCOUNT_TOKEN
  SPOTIFY_REDIRECT_PORT     port of http://127.0.0.1:<port>/callback (default 8888)
Test-only (never set in real use):
  SPOTIFY_API_BASE / SPOTIFY_ACCOUNTS_BASE  point the API somewhere else
  SPOTIFY_ACCESS_TOKEN                      use this token and skip the store
"""
import argparse
import base64
import datetime as dt
import hashlib
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

PLUGIN = "spotify"
API = os.environ.get("SPOTIFY_API_BASE", "https://api.spotify.com/v1").rstrip("/")
ACCOUNTS = os.environ.get("SPOTIFY_ACCOUNTS_BASE", "https://accounts.spotify.com").rstrip("/")

# The minimum the commands below need. Saving or removing Liked Songs (user-library-modify) is not requested.
SCOPES = [
    "user-read-playback-state",     # device list
    "user-modify-playback-state",   # play, move playback
    "user-read-currently-playing",  # now playing
    "user-read-recently-played",    # recently played
    "playlist-read-private",        # own playlists (private ones too): list and tracks
    "playlist-read-collaborative",  # collaborative playlists
    "playlist-modify-private",      # add to private playlists
    "playlist-modify-public",       # add to public playlists
    "user-library-read",            # read Liked Songs
]
TOKEN_FIELDS = ("refresh_token", "access_token", "expires_at")
MAX_RETRY_WAIT = 10  # seconds; a longer Retry-After stops the command instead
SANDBOX_HINT = ("If this runs inside Claude Code's Bash sandbox, run it outside the sandbox "
                "(the sandbox may not allow writes there)")


class CliError(Exception):
    def __init__(self, message, code=1, status=None, reason=None):
        super().__init__(message)
        self.code, self.status, self.reason = code, status, reason


class ItemMissing(CliError):
    """The store holds nothing yet (auth --client-id creates it)."""


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def setting(name, default=""):
    """An environment value, or default when it is empty or still an unsubstituted ${...} placeholder."""
    v = os.environ.get(name, "").strip()
    return default if not v or v.startswith("${") else v


def redirect_port():
    raw = setting("SPOTIFY_REDIRECT_PORT", "8888")
    m = re.fullmatch(r"(\d+)(\.0+)?", raw)  # userConfig numbers may arrive as "8888.0"
    port = int(m.group(1)) if m else 0
    if not 0 < port < 65536:
        raise CliError("SPOTIFY_REDIRECT_PORT is not a port number: %r" % raw, code=2)
    return port


# ---------------------------------------------------------------- token store

class OpStore:
    """One 1Password item, reached through a service account so op never prompts. Writes pass the item JSON on
    stdin, so no value appears in argv. The service account token goes only into the op subprocess's env."""

    def __init__(self, item, vault, token):
        self.item_name, self.vault, self._token, self._item = item, vault, token, None

    def _run(self, args, stdin=None):
        cmd = ["op", *args, "--vault", self.vault]
        env = dict(os.environ, OP_SERVICE_ACCOUNT_TOKEN=self._token)
        try:
            return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=60, env=env)
        except FileNotFoundError:
            raise CliError("the 1Password CLI (op) is not installed or not on PATH", code=3)
        except subprocess.TimeoutExpired:
            raise CliError("op timed out (no network access to 1Password? Inside Claude Code's Bash sandbox, run "
                           "it outside)", code=3)

    def item_id(self):
        return (self._item or {}).get("id")

    def _get_item(self):
        p = self._run(["item", "get", self.item_name, "--format", "json"])
        if p.returncode != 0:
            err = p.stderr.strip()[:300]
            if "isn't an item" in err or "not found" in err.lower():
                raise ItemMissing("1Password has no item '%s'. Create it with `spotify.py auth --client-id "
                                  "<Client ID>` (the setup skill)" % self.item_name, code=3)
            raise CliError("cannot read the 1Password item '%s': %s" % (self.item_name, err), code=3)
        return json.loads(p.stdout)

    def load(self):
        self._item = self._get_item()
        vals = {}
        for f in self._item.get("fields", []):
            key = f.get("label") or f.get("id")
            if key in ("client_id",) + TOKEN_FIELDS:
                vals[key] = f.get("value") or ""
        return vals

    def check_writable(self):
        pass  # op reports its own errors on save

    def create(self, client_id):
        # The client ID is not secret, so it may go in argv. save() writes the tokens later through stdin
        p = self._run(["item", "create", "--category", "API Credential", "--title", self.item_name,
                       "--format", "json", "client_id[text]=%s" % client_id])
        if p.returncode != 0:
            raise CliError("cannot create the 1Password item: %s" % p.stderr.strip()[:300], code=3)
        self._item = json.loads(p.stdout)

    def save(self, updates):
        item = self._item or self._get_item()
        fields = item.setdefault("fields", [])
        for key, value in updates.items():
            for f in fields:
                if (f.get("label") or f.get("id")) == key:
                    f["value"] = value
                    break
            else:
                fields.append({"id": key, "label": key,
                               "type": "STRING" if key in ("client_id", "expires_at") else "CONCEALED",
                               "value": value})
        self._item = item
        p = self._run(["item", "edit", item["id"]], stdin=json.dumps(item))
        if p.returncode != 0:
            raise CliError("cannot write to 1Password: %s" % p.stderr.strip()[:300], code=3)


class FileStore:
    """One JSON file, mode 0600, in a directory with mode 0700. Writes go through a temp file and a rename."""

    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            raise ItemMissing("no token file yet (%s). Create it with `spotify.py auth --client-id <Client ID>` "
                              "(the setup skill)" % self.path, code=3)
        except ValueError:
            # ItemMissing, so `auth --client-id` replaces the broken file
            raise ItemMissing("the token file %s is not valid JSON. Replace it with `spotify.py auth --client-id "
                              "<Client ID>`" % self.path, code=3)
        except OSError as e:
            raise CliError("cannot read the token file %s: %s" % (self.path, e.strerror), code=3)
        if not isinstance(data, dict):
            raise ItemMissing("the token file %s does not hold a JSON object. Replace it with `spotify.py auth "
                              "--client-id <Client ID>`" % self.path, code=3)
        return data

    def _fail(self, e, reason):
        return CliError("cannot write the token file %s: %s. %s" % (self.path, e.strerror, SANDBOX_HINT),
                        code=3, reason=reason)

    def _dir(self):
        d = os.path.dirname(self.path)
        if not os.path.isdir(d):
            os.makedirs(d, mode=0o700)
            os.chmod(d, 0o700)  # makedirs is subject to the umask
        return d

    def check_writable(self):
        """Called before asking Spotify for new tokens, so a refresh token is never received and then lost."""
        try:
            fd, tmp = tempfile.mkstemp(dir=self._dir(), prefix=".probe-")
            os.close(fd)
            os.unlink(tmp)
        except OSError as e:
            raise self._fail(e, "store_not_writable")

    def _write(self, data):
        try:
            fd, tmp = tempfile.mkstemp(dir=self._dir(), prefix=".token-", suffix=".tmp")  # mkstemp makes it 0600
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as e:
            raise self._fail(e, "store_write_failed")

    def create(self, client_id):
        self._write({"client_id": client_id})

    def save(self, updates):
        data = self.load()
        data.update(updates)
        self._write(data)


def token_file():
    data = setting("CLAUDE_PLUGIN_DATA")
    name = os.path.basename(os.path.normpath(data)) if data else ""
    if name != PLUGIN and not name.startswith(PLUGIN + "-"):
        # No fallback location: a second place would split the tokens between two files
        raise CliError("CLAUDE_PLUGIN_DATA is not this plugin's data directory (got %r). Run the command as the "
                       "spotify skill writes it, which passes CLAUDE_PLUGIN_DATA" % data, code=2)
    return os.path.join(data, PLUGIN, "token.json")


def op_store():
    """The 1password store works only through a service account: an interactive op would prompt on every command."""
    name = setting("SPOTIFY_OP_TOKEN_ENV")
    if not name:
        raise CliError("token_store = 1password needs op_token_env: the name of the environment variable that holds "
                       "your 1Password service account token. See the setup skill", code=3, reason="op_token_missing")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) or name.lower().startswith("ops_"):
        # Never echo it: someone may have pasted the token itself here
        raise CliError("op_token_env must be the NAME of an environment variable (letters, digits and _), not the "
                       "token itself. See the setup skill", code=2, reason="op_token_env_invalid")
    token = os.environ.get(name, "")
    if not token:
        raise CliError("the environment variable %s (op_token_env) is not set in Claude Code's environment. See the "
                       "setup skill" % name, code=3, reason="op_token_missing")
    vault = setting("SPOTIFY_OP_VAULT")
    if not vault:
        raise CliError("token_store = 1password needs op_vault: the vault (name or ID) the service account can read "
                       "and write. See the setup skill", code=2)
    return OpStore(setting("SPOTIFY_OP_ITEM", "Spotify Web API"), vault, token)


def store():
    kind = setting("SPOTIFY_TOKEN_STORE", "file").lower()
    if kind == "file":
        return FileStore(token_file())
    if kind == "1password":
        return op_store()
    raise CliError("unknown token store %r: use file or 1password" % kind, code=2)


def token_request(form, need):
    """PKCE: the form carries client_id instead of a client secret. need: fields the response must carry."""
    req = urllib.request.Request(ACCOUNTS + "/api/token", data=urllib.parse.urlencode(form).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        if "invalid_grant" in body:
            raise CliError("the refresh token is no longer valid (it expires 6 months after the authorization, or "
                           "access was revoked). Run `spotify.py auth` to approve in the browser again",
                           code=3, status=e.code, reason="invalid_grant")
        raise CliError("token endpoint error: %s" % body[:300], status=e.code)
    tok = None
    try:
        tok = json.loads(raw)
        if not isinstance(tok, dict) or any(not isinstance(tok.get(k), str) or not tok[k] for k in need):
            raise ValueError
        tok["expires_in"] = int(tok.get("expires_in") or 3600)
    except (ValueError, TypeError):  # never echo the body: it may hold a token
        raise CliError("the token endpoint returned an unexpected response (fields: %s)"
                       % (sorted(tok) if isinstance(tok, dict) else type(tok).__name__), code=3)
    return tok


def access_token():
    env = os.environ.get("SPOTIFY_ACCESS_TOKEN")
    if env:
        return env
    st = store()
    vals = st.load()
    if not vals.get("client_id"):
        raise CliError("the token store has no client_id. Run `spotify.py auth --client-id <Client ID>`", code=3)
    if not vals.get("refresh_token"):
        raise CliError("the token store has no refresh_token. Run `spotify.py auth` to approve in the browser",
                       code=3)
    try:
        exp = float(vals.get("expires_at") or 0)
    except ValueError:
        exp = 0
    if vals.get("access_token") and exp - 60 > time.time():
        return vals["access_token"]
    st.check_writable()
    tok = token_request({"grant_type": "refresh_token", "refresh_token": vals["refresh_token"],
                         "client_id": vals["client_id"]}, need=("access_token",))
    updates = {"access_token": tok["access_token"],
               "expires_at": str(int(time.time() + int(tok.get("expires_in", 3600))))}
    if tok.get("refresh_token"):  # replace it only when one comes back (not every time)
        updates["refresh_token"] = tok["refresh_token"]
    st.save(updates)
    return tok["access_token"]


# ---------------------------------------------------------------- HTTP

_bearer = None


def api(method, path, params=None, body=None):
    global _bearer
    if _bearer is None:
        _bearer = access_token()
    url = path if path.startswith("http") else API + path
    if params:
        q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if q:
            url += ("&" if "?" in url else "?") + q
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(3):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + _bearer)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw and r.status != 204 else None
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code == 429:
                try:
                    wait = max(int(e.headers.get("Retry-After") or 1), 1)
                except ValueError:
                    wait = 1
                if wait > MAX_RETRY_WAIT:  # never resend early: stop and say when it may be retried
                    raise CliError("rate limited: retry after %d seconds" % wait, status=429, reason="RETRY_AFTER_%d" % wait)
                if attempt < 2:
                    time.sleep(wait)
                    continue
            try:
                err = json.loads(raw)
            except ValueError:
                err = None
            err = err.get("error") if isinstance(err, dict) else None
            if isinstance(err, str):
                err = {"message": err}
            if not isinstance(err, dict):
                err = {}
            raise CliError(str(err.get("message") or raw[:200] or "HTTP %d" % e.code),
                           status=e.code, reason=err.get("reason"))
    raise CliError("still 429 after retrying", status=429)


def iter_items(path, params=None):
    """Yield items one by one, following next (reads only as many pages as needed)."""
    url, first = path, True
    while url:
        page = api("GET", url, params if first else None) or {}
        first = False
        for it in page.get("items", []):
            yield it
        url = page.get("next")


def collect(path, params=None, cap=None):
    res = []
    for it in iter_items(path, params):
        res.append(it)
        if cap and len(res) >= cap:
            break
    return res


# ---------------------------------------------------------------- shaping

def track_brief(t):
    if not t:
        return {}
    return {"name": t.get("name"), "artists": [a.get("name") for a in t.get("artists", [])],
            "album": (t.get("album") or {}).get("name"), "uri": t.get("uri"),
            "duration_ms": t.get("duration_ms")}


def parse_time(s):
    """ISO 8601 (Z allowed; no offset means local time) to a UTC datetime."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.astimezone()
    return d.astimezone(dt.timezone.utc)


def my_playlists():
    uid = api("GET", "/me")["id"]
    res = []
    for p in iter_items("/me/playlists", {"limit": 50}):
        if not p:
            continue
        res.append({"id": p["id"], "name": p.get("name"), "owned": (p.get("owner") or {}).get("id") == uid,
                    "collaborative": bool(p.get("collaborative")), "public": p.get("public"),
                    "total": (p.get("items") or p.get("tracks") or {}).get("total")})
    return res


def resolve_playlist(ref, editable=False):
    """An ID, URI, URL or own playlist name (exact match, else a single partial match) to a playlist ID."""
    if ref.startswith("spotify:playlist:"):
        return ref.split(":")[-1]
    if "open.spotify.com/playlist/" in ref:
        return ref.split("/playlist/")[1].split("?")[0]
    pls = my_playlists()
    if editable:
        pls = [p for p in pls if p["owned"] or p["collaborative"]]
    for p in pls:
        if p["id"] == ref:
            return p["id"]
    exact = [p for p in pls if p["name"] == ref]
    if len(exact) == 1:
        return exact[0]["id"]
    part = [p for p in pls if ref.lower() in (p["name"] or "").lower()]
    if exact or len(part) != 1:
        cands = [p["name"] for p in (exact or part)]
        raise CliError("playlist '%s' does not match exactly one playlist (candidates: %s)" % (ref, cands or "none"),
                       code=2)
    return part[0]["id"]


def playlist_items(pid, cap=None):
    rows = []
    for it in iter_items("/playlists/%s/items" % pid, {"limit": 50}):
        t = it.get("item")  # item since 2026-02 (track is deprecated)
        if t and t.get("type", "track") == "track":
            rows.append({**track_brief(t), "added_at": it.get("added_at")})
            if cap and len(rows) >= cap:  # count tracks, not episodes or removed items
                break
    return rows


def resolve_device(ref):
    devs = (api("GET", "/me/player/devices") or {}).get("devices", [])
    for d in devs:
        if d.get("id") == ref:
            return d
    exact = [d for d in devs if d.get("name") == ref]
    part = [d for d in devs if ref.lower() in (d.get("name") or "").lower()]
    hit = exact if len(exact) == 1 else part
    if len(hit) != 1:
        raise CliError("device '%s' does not match exactly one device (devices visible now: %s). Only devices with "
                       "the Spotify app open are listed" % (ref, [d.get("name") for d in devs] or "none"), code=2,
                       reason="DEVICE_NOT_FOUND")
    if not hit[0].get("id"):
        raise CliError("device '%s' has no ID the Web API can address; open Spotify on it again or pick another"
                       % hit[0].get("name"), code=2, reason="DEVICE_NOT_FOUND")
    if hit[0].get("is_restricted"):
        raise CliError("device '%s' does not accept Web API commands (is_restricted)" % hit[0].get("name"), code=2)
    return hit[0]


# ---------------------------------------------------------------- commands

def cmd_devices(a):
    devs = (api("GET", "/me/player/devices") or {}).get("devices", [])
    out([{k: d.get(k) for k in ("name", "id", "type", "is_active", "is_restricted", "volume_percent")}
         for d in devs])


def cmd_play(a):
    params = {"device_id": resolve_device(a.device)["id"]} if a.device else None
    body = {}
    if a.context:
        body["context_uri"] = a.context
        if a.offset_uri:
            body["offset"] = {"uri": a.offset_uri}
    elif a.uris:
        body["uris"] = a.uris
    api("PUT", "/me/player/play", params, body or None)
    out({"ok": True, "device_id": (params or {}).get("device_id"), **body})


def cmd_transfer(a):
    d = resolve_device(a.device)
    api("PUT", "/me/player", body={"device_ids": [d["id"]], "play": bool(a.play)})
    out({"ok": True, "device": d.get("name"), "device_id": d["id"], "play": bool(a.play)})


def cmd_now(a):
    r = api("GET", "/me/player/currently-playing")
    if not r:
        out({"playing": False})
        return
    out({"playing": bool(r.get("is_playing")), "progress_ms": r.get("progress_ms"),
         "type": r.get("currently_playing_type"), "track": track_brief(r.get("item")),
         "device": (r.get("device") or {}).get("name"), "context": (r.get("context") or {}).get("uri")})


def cmd_recent(a):
    params = {"limit": a.limit}
    if a.after:
        params["after"] = int(parse_time(a.after).timestamp() * 1000)
    r = api("GET", "/me/player/recently-played", params) or {}
    out([{"played_at": i.get("played_at"), **track_brief(i.get("track"))} for i in r.get("items", [])])


def cmd_playlists(a):
    pls = my_playlists()
    out(pls if a.all else [p for p in pls if p["owned"] or p["collaborative"]])


def cmd_tracks(a):
    out(playlist_items(resolve_playlist(a.playlist), cap=a.limit))


def cmd_taste(a):
    pls = [p for p in my_playlists() if p["owned"] or p["collaborative"]]
    if a.playlist:
        ids = {resolve_playlist(x) for x in a.playlist}
        pls = [p for p in pls if p["id"] in ids]
    res = []
    for p in pls:
        rows = playlist_items(p["id"], cap=a.max_tracks)
        counts = {}
        for r in rows:
            for n in r["artists"]:
                counts[n] = counts.get(n, 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:a.top]
        recent = sorted(rows, key=lambda r: r.get("added_at") or "", reverse=True)[:a.sample]
        res.append({"playlist": p["name"], "id": p["id"], "total": p["total"], "read": len(rows),
                    "top_artists": [{"artist": n, "count": c} for n, c in top],
                    "recently_added": ["%s / %s" % (r["name"], ", ".join(r["artists"])) for r in recent]})
    out(res)


def cmd_search(a):
    r = api("GET", "/search", {"q": a.query, "type": "track", "limit": a.limit, "market": a.market}) or {}
    out([track_brief(t) for t in (r.get("tracks") or {}).get("items", []) if t])


def cmd_add(a):
    for u in a.uris:
        if not u.startswith("spotify:track:"):
            raise CliError("pass track URIs (spotify:track:...): %s" % u, code=2)
    pid = resolve_playlist(a.playlist, editable=True)
    have = {r["uri"] for r in playlist_items(pid)}
    todo, skipped = [], []
    for u in a.uris:
        (skipped if u in have or u in todo else todo).append(u)
    for i in range(0, len(todo), 100):  # at most 100 per request
        api("POST", "/playlists/%s/items" % pid, body={"uris": todo[i:i + 100]})
    out({"playlist_id": pid, "added": todo, "skipped_duplicates": skipped})


def cmd_liked(a):
    since = parse_time(a.since) if a.since else None
    among = set(a.among or [])
    res = []
    for n, it in enumerate(iter_items("/me/tracks", {"limit": 50})):
        if n >= a.scan or (since and parse_time(it["added_at"]) < since):
            break  # newest first, so everything after this is older
        t = it.get("track")
        if t and (not among or t.get("uri") in among):
            res.append({"added_at": it["added_at"], **track_brief(t)})
    out(res)


def cmd_auth(a):
    """Authorization Code + PKCE (no client secret). Receives the callback locally and stores the refresh token.
    Creates the store entry with --client-id when there is none."""
    st = store()
    try:
        vals = st.load()
    except ItemMissing:
        if not a.client_id:
            raise
        st.create(a.client_id)
        vals = {"client_id": a.client_id}
    if a.client_id:
        # A changed client ID is saved only together with the tokens it earns, so a failed run keeps the old pair
        vals["client_id"] = a.client_id
    if not vals.get("client_id"):
        raise CliError("no client_id. Pass it with `spotify.py auth --client-id <Client ID>`", code=2)
    port = a.port or redirect_port()
    st.check_writable()  # before the user approves, so the tokens are not lost afterwards
    redirect = "http://127.0.0.1:%d/callback" % port
    state = secrets.token_urlsafe(16)
    verifier = secrets.token_urlsafe(64)  # 86 characters (within 43 to 128)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    url = ACCOUNTS + "/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": vals["client_id"], "scope": " ".join(SCOPES),
        "redirect_uri": redirect, "state": state, "show_dialog": "true",
        "code_challenge_method": "S256", "code_challenge": challenge})
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        timeout = 5  # a connection that stalls can't hold the --wait deadline

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            got.update({k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Spotify authorization received. You can close this tab.")

        def log_message(self, *args):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        raise CliError("cannot listen on 127.0.0.1:%d: %s. Pick another port in both the developer app's Redirect "
                       "URI and redirect_port" % (port, e.strerror), code=2)
    srv.timeout = 5
    sys.stderr.write("Open this URL in a browser and approve (waiting %d seconds):\n%s\n" % (a.wait, url))
    sys.stderr.flush()
    if not a.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # no browser here: the URL above is enough
            pass
    deadline = time.time() + a.wait
    while not got and time.time() < deadline:
        srv.handle_request()
    srv.server_close()
    if not got:
        raise CliError("no callback arrived in time", code=2)
    if got.get("state") != state:
        raise CliError("state does not match (a callback from another authorization)", code=2)
    if "error" in got:
        raise CliError("authorization was not granted: %s" % got["error"], code=2)
    tok = token_request({"grant_type": "authorization_code", "code": got["code"], "redirect_uri": redirect,
                         "client_id": vals["client_id"], "code_verifier": verifier},
                        need=("access_token", "refresh_token"))
    st.save({"client_id": vals["client_id"], "refresh_token": tok["refresh_token"], "access_token": tok["access_token"],
             "expires_at": str(int(time.time() + int(tok.get("expires_in", 3600))))})
    res = {"ok": True, "scope": tok.get("scope", "").split()}
    if isinstance(st, OpStore):
        res["op_item_id"] = st.item_id()  # setting op_item to this ID saves requests
    out(res)


def cmd_check(a):
    m = api("GET", "/me")
    out({"ok": True, "user_id": m.get("id"), "display_name": m.get("display_name")})


def positive(v):
    n = int(v)
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return n


def build_parser():
    p = argparse.ArgumentParser(prog="spotify.py", description="Spotify Web API CLI")
    sp = p.add_subparsers(dest="cmd", required=True)

    s = sp.add_parser("auth", help="approve in the browser (first time, or after the refresh token expires) and store the tokens")
    s.add_argument("--port", type=int, help="default: SPOTIFY_REDIRECT_PORT, else 8888")
    s.add_argument("--wait", type=int, default=300)
    s.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    s.add_argument("--client-id", help="Client ID of your developer app (first time, or to change it)")
    s.set_defaults(fn=cmd_auth)

    sp.add_parser("check", help="check that auth works").set_defaults(fn=cmd_check)
    sp.add_parser("devices", help="devices that can play").set_defaults(fn=cmd_devices)

    s = sp.add_parser("play", help="play (device, tracks or a playlist)")
    s.add_argument("--device", help="device name (partial match) or ID; default is the active device")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--uris", nargs="+", help="track URIs (played in this order)")
    g.add_argument("--context", help="playlist or album URI")
    s.add_argument("--offset-uri", help="URI of the track in --context to start with")
    s.set_defaults(fn=cmd_play)

    s = sp.add_parser("transfer", help="move playback to another device")
    s.add_argument("--device", required=True)
    s.add_argument("--play", action="store_true", help="start playing on the new device")
    s.set_defaults(fn=cmd_transfer)

    sp.add_parser("now", help="what is playing now").set_defaults(fn=cmd_now)

    s = sp.add_parser("recent", help="recently played tracks (newest first)")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--after", help="only after this time (ISO 8601)")
    s.set_defaults(fn=cmd_recent)

    s = sp.add_parser("playlists", help="your playlists (default: owned and collaborative)")
    s.add_argument("--all", action="store_true", help="also include followed playlists of others")
    s.set_defaults(fn=cmd_playlists)

    s = sp.add_parser("tracks", help="tracks in a playlist")
    s.add_argument("playlist", help="name, ID, URI or URL")
    s.add_argument("--limit", type=positive, help="at most this many tracks")
    s.set_defaults(fn=cmd_tracks)

    s = sp.add_parser("taste", help="taste summary per playlist (top artists, recently added tracks)")
    s.add_argument("--playlist", nargs="+", help="limit to these playlists (default: all of your own)")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--sample", type=int, default=10)
    s.add_argument("--max-tracks", type=int, default=500)
    s.set_defaults(fn=cmd_taste)

    s = sp.add_parser("search", help="search tracks to get URIs")
    s.add_argument("query", help='for example "track:<title> artist:<artist>"')
    s.add_argument("--limit", type=int, default=5, help="1 to 10")
    s.add_argument("--market", default=None)
    s.set_defaults(fn=cmd_search)

    s = sp.add_parser("add", help="add tracks to a playlist (tracks already in it are skipped)")
    s.add_argument("playlist", help="name, ID, URI or URL (owned or collaborative)")
    s.add_argument("uris", nargs="+")
    s.set_defaults(fn=cmd_add)

    s = sp.add_parser("liked", help="tracks saved to Liked Songs (newest first)")
    s.add_argument("--since", help="saved at or after this time (ISO 8601)")
    s.add_argument("--among", nargs="+", help="only these URIs, if saved")
    s.add_argument("--scan", type=int, default=500, help="how many to read at most")
    s.set_defaults(fn=cmd_liked)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        a.fn(a)
    except CliError as e:
        sys.stderr.write(json.dumps({"error": str(e), "status": e.status, "reason": e.reason},
                                    ensure_ascii=False) + "\n")
        return e.code
    except urllib.error.URLError as e:
        sys.stderr.write(json.dumps({"error": "cannot connect: %s" % e.reason}, ensure_ascii=False) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
