# -*- coding: utf-8 -*-
"""Cases for skills/spotify/scripts/spotify.py, one verdict row per case in cases.json.

Each case runs the script against a local mock Spotify (127.0.0.1, random port) with a fresh temp root holding the plugin
data directory (named like Claude Code names it, `spotify-<marketplace>`). PATH is a recording `op` stub plus the system
directories, so the real 1Password CLI is never reached: cases with the 1password store check what the stub saw, and every
other case checks that `op` was never called. Files are created under umask 022, so the mode checks prove the script sets
0600 / 0700 itself. Expected values come from cases.json (Spotify's reference examples and SKILL.md), not from the
script's output.
"""
import base64
import hashlib
import socket
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "skills", "spotify", "scripts", "spotify.py")
DATA_NAME = "spotify-test-marketplace"
SYSTEM_PATH = "/usr/bin:/bin"

OP_STUB = """#!%s
# Recording stand-in for the 1Password CLI: logs argv (and stdin for edit) and serves one item from item.json
import json, os, sys
d = os.environ["OP_STUB_DIR"]
args = sys.argv[1:]
stdin = sys.stdin.read() if args[:2] == ["item", "edit"] else ""
with open(os.path.join(d, "calls.jsonl"), "a") as f:
    f.write(json.dumps({"argv": args, "stdin": stdin, "sa_token": os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")}) + "\\n")
path = os.path.join(d, "item.json")
if args[:2] == ["item", "get"]:
    if not os.path.exists(path):
        sys.stderr.write("%%s isn't an item in any vault.\\n" %% args[2])
        sys.exit(1)
    print(open(path).read())
elif args[:2] == ["item", "create"]:
    item = {"id": "stubcreated", "title": args[args.index("--title") + 1], "fields": []}
    for a in args:
        if a.startswith("client_id[text]="):
            item["fields"].append({"id": "client_id", "label": "client_id", "value": a.split("=", 1)[1]})
    json.dump(item, open(path, "w"))
    print(json.dumps(item))
elif args[:2] == ["item", "edit"]:
    json.dump(json.loads(stdin), open(path, "w"))
    print(stdin)
else:
    sys.exit(2)
"""


class Mock:
    def __init__(self):
        self.routes, self.calls, self.log = {}, {}, []
        mock = self

        class H(BaseHTTPRequestHandler):
            def _handle(self):
                u = urllib.parse.urlparse(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode() if n else ""
                rec = {"method": self.command, "path": u.path,
                       "query": {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()},
                       "auth": self.headers.get("Authorization"), "raw": raw,
                       "line": "%s %s%s" % (self.command, u.path, ("?" + u.query) if u.query else "")}
                try:
                    rec["body"] = json.loads(raw) if raw else None
                except ValueError:
                    rec["body"] = None
                rec["form"] = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()} if rec["body"] is None else None
                mock.log.append(rec)
                key = "%s %s" % (self.command, u.path)
                resps = mock.routes.get(key)
                if not resps:
                    self.send_response(599)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": {"message": "mock: no route " + key}}).encode())
                    return
                # Each call to the same key takes the next response in order (pagination); the last one repeats
                i = mock.calls.get(key, 0)
                mock.calls[key] = i + 1
                r = resps[min(i, len(resps) - 1)]
                self.send_response(r.get("status", 200))
                for hk, hv in (r.get("headers") or {}).items():
                    self.send_header(hk, hv)
                body = json.dumps(r["json"], ensure_ascii=False).encode() if "json" in r else b""
                if body:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)

            do_GET = do_PUT = do_POST = do_DELETE = _handle

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def reset(self, routes):
        text = json.dumps(routes, ensure_ascii=False).replace("{BASE}", self.base)
        self.routes, self.calls, self.log = json.loads(text), {}, []


def subset(exp, got):
    """Whether exp is contained in got (dict: subset of keys; list: same length, element by element)."""
    if isinstance(exp, dict):
        return isinstance(got, dict) and all(k in got and subset(v, got[k]) for k, v in exp.items())
    if isinstance(exp, list):
        return isinstance(got, list) and len(exp) == len(got) and all(subset(a, b) for a, b in zip(exp, got))
    return exp == got


def expand(args):
    res = []
    for a in args:
        m = re.fullmatch(r"@gen:(.*):(\d+):(\d+)", a)
        if m:
            tmpl, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
            res += [re.sub(r"\{i:(\w+)\}", lambda mm: format(i, mm.group(1)), tmpl) for i in range(lo, hi + 1)]
        else:
            res.append(a)
    return res


def req_matches(exp, rec):
    if exp.get("method") and exp["method"] != rec["method"]:
        return False
    if exp.get("path") and exp["path"] != rec["path"]:
        return False
    if "query" in exp and not subset(exp["query"], {k: v for k, v in rec["query"].items() if k in exp["query"]}):
        return False
    if "body" in exp and exp["body"] != rec["body"]:
        return False
    if "form" in exp and not subset(exp["form"], rec["form"] or {}):
        return False
    if "auth" in exp and exp["auth"] != rec["auth"]:
        return False
    uris = (rec["body"] or {}).get("uris") if isinstance(rec["body"], dict) else None
    if "body_uris_len" in exp and (uris is None or len(uris) != exp["body_uris_len"]):
        return False
    if "body_first_uri" in exp and (not uris or uris[0] != exp["body_first_uri"]):
        return False
    return True


NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the callback goes straight to 127.0.0.1


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_auth(env, step):
    """Starts auth in the background and calls back with the state from the printed URL (in place of a browser).
    Keeps the URL's query on the step for the PKCE check."""
    args = [sys.executable, "-B", SCRIPT, "auth", "--no-open", "--wait", "20", *step["run"]]
    p = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True)
    timer = threading.Timer(60, p.kill)  # one deadline from start to exit, so a stuck child fails only this case
    timer.start()
    try:
        return _drive_auth(p, args, step)
    finally:
        timer.cancel()
        if p.poll() is None:
            p.kill()
            p.communicate()


def _drive_auth(p, args, step):
    p.stderr.readline()
    url = p.stderr.readline().strip()
    q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(url).query).items()}
    if "redirect_uri" not in q:
        p.kill()
        out, err = p.communicate()
        return None, "no authorize URL printed: %s %s" % (url, err[:200])
    step["_authorize"] = q
    state = q.get("state") if step["auth_callback"] == "ok" else "wrong-state"
    cb = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": "eval-code", "state": state})
    for _ in range(50):  # wait until the server listens
        try:
            NO_PROXY.open(cb, timeout=2).read()
            break
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.1)
    out, err = p.communicate(timeout=30)
    return subprocess.CompletedProcess(args, p.returncode, out, err), None


def pkce_ok(step, log):
    q = step.get("_authorize") or {}
    forms = [r["form"] for r in log if r["path"] == "/api/token" and r["form"]
             and r["form"].get("grant_type") == "authorization_code"]
    if q.get("code_challenge_method") != "S256" or not forms:
        return False
    v = forms[-1].get("code_verifier") or ""
    ch = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    return 43 <= len(v) <= 128 and ch == q.get("code_challenge")


def mode(path):
    return format(stat.S_IMODE(os.stat(path).st_mode), "o")


def run_case(mock, case, root):
    fails = []
    # A free port per case for auth's callback server, so a busy fixed port can't fail a correct script
    case = json.loads(json.dumps(case).replace("{AUTH_PORT}", str(free_port())))
    mock.reset(case.get("routes", {}))
    data = os.path.join(root, DATA_NAME)
    tdir = os.path.join(data, "spotify")
    tf = os.path.join(tdir, "token.json")
    stub = os.path.join(root, "stub")
    os.makedirs(stub)
    with open(os.path.join(stub, "op"), "w") as f:
        f.write(OP_STUB % sys.executable)
    os.chmod(os.path.join(stub, "op"), 0o755)
    if "op_item" in case:
        with open(os.path.join(stub, "item.json"), "w") as f:
            json.dump(case["op_item"], f)
    base = {k: v for k, v in os.environ.items() if not k.startswith(("SPOTIFY_", "CLAUDE_PLUGIN_"))
            and not k.startswith("OP_") and k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")}
    base["NO_PROXY"] = "127.0.0.1,localhost"
    base.update({"PATH": stub + ":" + SYSTEM_PATH, "OP_STUB_DIR": stub, "CLAUDE_PLUGIN_DATA": data,
                 "SPOTIFY_API_BASE": mock.base + "/v1", "SPOTIFY_ACCOUNTS_BASE": mock.base})
    if "token_file_raw" in case:
        os.makedirs(tdir)
        os.chmod(tdir, 0o700)
        with open(tf, "w") as f:
            f.write(case["token_file_raw"])
    if "token_file" in case:
        os.makedirs(tdir)
        os.chmod(tdir, 0o700)  # as auth leaves it; the file itself starts at 644 so a write-back must make it 600
        with open(tf, "w") as f:
            json.dump(case["token_file"], f)
    elif not case.get("token_file_absent") and "token_file_raw" not in case:
        base["SPOTIFY_ACCESS_TOKEN"] = "eval-token"
    base.update(case.get("env") or {})
    if case.get("chmod_token_dir"):
        os.chmod(tdir, int(case["chmod_token_dir"], 8))
    for n, step in enumerate(case["steps"], 1):
        if step.get("expire_token_file"):
            with open(tf) as f:
                d = json.load(f)
            d["expires_at"] = "1000"
            with open(tf, "w") as f:
                json.dump(d, f)
            continue
        if "check_token_file" in step:
            with open(tf) as f:
                d = json.load(f)
            if not subset(step["check_token_file"], d):
                fails.append("step %d: stored values changed too early: client_id=%s" % (n, d.get("client_id")))
            continue
        env = dict(base, **(step.get("env") or {}))
        if step.get("plugin_data"):
            env["CLAUDE_PLUGIN_DATA"] = os.path.join(root, step["plugin_data"])
            os.makedirs(env["CLAUDE_PLUGIN_DATA"], exist_ok=True)
        before = len(mock.log)
        if "auth_callback" in step:
            p, err = run_auth(env, step)
            if err:
                fails.append("step %d (auth): %s" % (n, err))
                continue
        else:
            p = subprocess.run([sys.executable, "-B", SCRIPT, *expand(step["run"])], env=env,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        tag = "step %d (%s)" % (n, " ".join(step["run"][:2]))
        for s in step.get("expect_step_not_requested", []):
            hits = [r["line"] for r in mock.log[before:] if s in r["line"]]
            if hits:
                fails.append("%s: requested '%s' during this step: %s" % (tag, s, hits[:3]))
        if p.returncode != step.get("expect_code", 0):
            fails.append("%s: exit %d (want %d) stderr=%s" % (tag, p.returncode, step.get("expect_code", 0),
                                                              p.stderr.strip()[:300]))
            continue
        got = None
        if "expect_json" in step or "expect_json_len" in step:
            try:
                got = json.loads(p.stdout)
            except ValueError:
                fails.append("%s: stdout is not JSON: %s" % (tag, p.stdout[:200]))
                continue
        if "expect_json" in step and not subset(step["expect_json"], got):
            fails.append("%s: output differs: %s" % (tag, json.dumps(got, ensure_ascii=False)[:400]))
        for k, ln in (step.get("expect_json_len") or {}).items():
            if len(got.get(k) or []) != ln:
                fails.append("%s: %s has %d items (want %d)" % (tag, k, len(got.get(k) or []), ln))
        for s in step.get("expect_stdout_not_contains", []):
            if s in p.stdout:
                fails.append("%s: stdout shows '%s', which must not appear" % (tag, s))
        for s in step.get("expect_stderr_not_contains", []):
            if s in p.stderr:
                fails.append("%s: stderr shows '%s', which must not appear" % (tag, s))
        for s in step.get("expect_stderr_contains", []):
            if s not in p.stderr:
                fails.append("%s: stderr lacks '%s': %s" % (tag, s, p.stderr.strip()[:300]))
        for k, v in (step.get("expect_authorize") or {}).items():
            if (step.get("_authorize") or {}).get(k) != v:
                fails.append("%s: authorize URL %s is %r (want %r)" % (tag, k, (step.get("_authorize") or {}).get(k), v))
        if step.get("expect_pkce") and not pkce_ok(step, mock.log):
            fails.append("%s: PKCE mismatch (SHA-256 of code_verifier is not code_challenge)" % tag)
    if case.get("chmod_token_dir"):
        os.chmod(tdir, 0o700)
    # The expected requests arrived in this order (others may come in between)
    pos = 0
    for exp in case.get("expect_requests", []):
        while pos < len(mock.log) and not req_matches(exp, mock.log[pos]):
            pos += 1
        if pos >= len(mock.log):
            fails.append("request missing (or out of order): %s" % json.dumps(exp, ensure_ascii=False))
            break
        pos += 1
    for s in case.get("expect_not_requested", []):
        hits = [r["line"] for r in mock.log if s in r["line"]]
        if hits:
            fails.append("request that must not happen '%s': %s" % (s, hits[:3]))
    for key, want in (case.get("expect_request_count") or {}).items():
        got = len([r for r in mock.log if "%s %s" % (r["method"], r["path"]) == key])
        if got != want:
            fails.append("%s was requested %d times (want %d)" % (key, got, want))
    no_route = [r["line"] for r in mock.log if "%s %s" % (r["method"], r["path"]) not in mock.routes]
    if no_route:
        fails.append("hit a path the mock does not serve: %s" % no_route[:3])
    if "expect_token_file" in case:
        if not os.path.exists(tf):
            fails.append("token file was not written: %s" % tf)
        else:
            with open(tf) as f:
                d = json.load(f)
            if not subset(case["expect_token_file"], d):
                fails.append("stored tokens differ: refresh=%s access=%s" % (d.get("refresh_token"), d.get("access_token")))
    want_mode = case.get("expect_token_mode")
    if want_mode and os.path.exists(tf):
        if mode(tf) != want_mode["file"] or mode(tdir) != want_mode["dir"]:
            fails.append("modes: token.json %s, directory %s (want %s / %s)"
                         % (mode(tf), mode(tdir), want_mode["file"], want_mode["dir"]))
        leftovers = [x for x in os.listdir(tdir) if x != "token.json"]
        if leftovers:
            fails.append("temp files left next to token.json: %s" % leftovers)
    if case.get("expect_no_token_file") and os.path.exists(tf):
        fails.append("a token file was written although it must not be: %s" % tf)
    if case.get("expect_dir_empty"):
        left = os.listdir(os.path.join(root, case["expect_dir_empty"]))
        if left:
            fails.append("wrote into another plugin's data directory: %s" % left)
    calls_path = os.path.join(stub, "calls.jsonl")
    calls = [json.loads(x) for x in open(calls_path)] if os.path.exists(calls_path) else []
    if "expect_op_calls" in case:
        argvs = [c["argv"] for c in calls]
        if argvs != case["expect_op_calls"]:
            fails.append("op calls %s (want %s)" % (argvs, case["expect_op_calls"]))
        stdin = "".join(c["stdin"] for c in calls)
        for s in case.get("expect_op_stdin_contains", []):
            if s not in stdin:
                fails.append("op item edit stdin lacks '%s'" % s)
        if "expect_op_sa_token" in case:
            got_tokens = sorted({c["sa_token"] for c in calls}, key=str)
            if got_tokens != [case["expect_op_sa_token"]]:
                fails.append("op got OP_SERVICE_ACCOUNT_TOKEN %s, not the value of the variable op_token_env names"
                             % ["<set>" if t else t for t in got_tokens])
        secrets_in_argv = [a for c in calls for a in c["argv"] if "refresh" in a or "access" in a]
        if secrets_in_argv:
            fails.append("a token appeared in op's argv: %s" % secrets_in_argv)
    elif calls:
        fails.append("op was called although the store is not 1password: %s" % [c["argv"] for c in calls])
    return fails


def main():
    with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
        spec = json.load(f)
    want = set(sys.argv[1:])
    cases = [c for c in spec["cases"] if not want or c["id"] in want]
    os.umask(0o022)
    mock = Mock()
    for c in cases:
        root = tempfile.mkdtemp(prefix="spotify-case-")
        try:
            fails = run_case(mock, c, root)
        except Exception as e:  # a crash in one case is that case's failure, not the end of the run
            fails = ["runner error: %r" % e]
        finally:
            shutil.rmtree(root, ignore_errors=True)
        for x in fails:
            print("     - " + x)
        print("  %s -> %s (expect PASS)" % (c["id"], "FAIL" if fails else "PASS"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
