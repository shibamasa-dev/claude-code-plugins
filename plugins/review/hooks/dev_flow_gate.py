#!/usr/bin/env python3
"""dev-flow-gate: dev-flow スキルの手順のうち、飛ばすと事故になる3か所を止めるフック。

  - PreToolUse  (PR 作成): 本文に Closes / Refs（または `Refs: none (verbal request)`）と
                           `Arch-Review:` の欄が無ければ deny
  - PostToolUse (PR 作成): PR と Closes 先を記録し、次の段（レビュー待ち）を伝える
  - Stop                 : このセッションで PR を作ったのに待ち（PR イベントの購読か Monitor）を
                           始めていなければ、PR ごとに 1 回だけ block
  - PreToolUse  (マージ) : 記録した Closes 先の issue に、このセッションで `## 結果` を
                           書いた（または読んで確かめた）記録が無ければ deny
  - PostToolUse (マージ) : 記録の無い PR（別セッションで作ったもの）をマージしたら、確かめるよう一言返す

GitHub を自分では読みに行かない。判定に使うのはセッション中のツール呼び出し（名前・入力・結果）だけ。
コネクタ（mcp__*__create_pull_request など）と gh の両方を見る。
状態は <CLAUDE_PLUGIN_DATA or ~/.claude/state>/dev-flow-gate/<session_id>.json。
何が起きても例外で落ちず exit 0（deny と block だけが「止める」出力）。
"""
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime

STATE_DIR = os.path.join(os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.expanduser("~/.claude/state"),
                         "dev-flow-gate")
GC_DAYS = 30
TAG = "[dev-flow-gate]"

CLOSE_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+((?:[\w.-]+/[\w.-]+)?#\d+)", re.I)
REFS_RE = re.compile(r"\brefs?\s*:?\s+(?:(?:[\w.-]+/[\w.-]+)?#\d+|none\s*\(verbal request\))", re.I)
ARCH_RE = re.compile(r"^\s*Arch-Review:\s*(?:not-needed|approved)\s*[—–-]+\s*\S", re.I | re.M)
RESULT_RE = re.compile(r"^##\s*(?:結果|次回への引き継ぎ|Results?)\s*$", re.M)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
HEREDOC_RE = re.compile(r"(<<-?\s*(['\"]?)(\w+)\2)[^\n]*\n.*?\n\s*\3\s*(?:\n|$)", re.S)
PR_URL_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)")


# ------------------------------------------------------------------ state io
def _path(session_id):
    return os.path.join(STATE_DIR, f"{session_id}.json")


class State:
    """flock 付き read-modify-write。並列のツール呼び出しで同時に来ても壊れない。"""

    def __init__(self, session_id):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.p = _path(session_id)
        self.lock = self.p + ".lock"

    def __enter__(self):
        self.lf = open(self.lock, "w")
        fcntl.flock(self.lf, fcntl.LOCK_EX)
        try:
            with open(self.p) as f:
                self.d = json.load(f)
        except Exception:
            self.d = {}
        self.d.setdefault("prs", {})
        self.d.setdefault("results", [])
        return self

    def __exit__(self, *a):
        tmp = self.p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p)
        fcntl.flock(self.lf, fcntl.LOCK_UN)
        self.lf.close()


def read_state(session_id):
    try:
        with open(_path(session_id)) as f:
            d = json.load(f)
    except Exception:
        return {"prs": {}, "results": []}
    d.setdefault("prs", {})
    d.setdefault("results", [])
    return d


def now():
    return datetime.now().isoformat(timespec="seconds")


def gc():
    try:
        cutoff = time.time() - GC_DAYS * 86400
        for n in os.listdir(STATE_DIR):
            fp = os.path.join(STATE_DIR, n)
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
    except Exception:
        pass


# ------------------------------------------------------------------ helpers
def repo_from_cwd(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd or ".", "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=2)
        m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", r.stdout.strip())
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return None


def branch_from_cwd(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd or ".", "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=2)
        b = r.stdout.strip()
        return b if r.returncode == 0 and b and b != "HEAD" else None
    except Exception:
        return None


def norm_ref(ref, default_repo):
    """`#5` → `owner/repo#5`（大文字小文字は GitHub と同じく区別しない）。"""
    if ref.startswith("#"):
        if not default_repo:
            return None
        ref = default_repo + ref
    return ref.lower()


def body_missing(body):
    """PR 本文に足りない印のリスト。HTML コメントの中（テンプレートの説明）は数えない。"""
    text = HTML_COMMENT_RE.sub("", body or "")
    missing = []
    if not (CLOSE_RE.search(text) or REFS_RE.search(text)):
        missing.append("`Closes #N` か `Refs #N`（issue の無い依頼なら `Refs: none (verbal request)`）")
    if not ARCH_RE.search(text):
        missing.append("`Arch-Review: not-needed — <理由>` か `Arch-Review: approved — <GO の在りか>`")
    return missing


def closes_of(body, repo):
    text = HTML_COMMENT_RE.sub("", body or "")
    out = []
    for m in CLOSE_RE.finditer(text):
        r = norm_ref(m.group(1), repo)
        if r and r not in out:
            out.append(r)
    return out


def text_of(tr):
    """ツールの結果を検索用の1本の文字列にする（JSON 文字列の中の改行も戻す）。"""
    if tr is None:
        return ""
    if isinstance(tr, str):
        try:
            tr = json.loads(tr)
        except Exception:
            return tr
    if isinstance(tr, dict) and isinstance(tr.get("stdout"), str):
        return tr["stdout"]
    parts = []

    def walk(x):
        if isinstance(x, str):
            # コネクタの結果は [{"type":"text","text":"<JSON>"}] の形が多い。中の JSON も開いて改行を戻す
            if x[:1] in "{[":
                try:
                    walk(json.loads(x))
                    return
                except Exception:
                    pass
            parts.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(tr)
    return "\n".join(parts)


def failed(tr):
    """Bash の gh が失敗していたら True（成功したときだけ記録する）。"""
    if isinstance(tr, dict):
        if tr.get("interrupted") or tr.get("is_error"):
            return True
        err = tr.get("stderr") or ""
        if err and re.search(r"(?i)\b(error|failed|could not|HTTP [45]\d\d|GraphQL)\b", err):
            return True
    return False


# --------------------------------------------------------------- gh parsing
def gh_commands(command):
    """Bash コマンドから gh の呼び出しを (positional, options, raw_tokens) で返す。

    ヒアドキュメントの中身は読み飛ばす（本文の ' や # で字句解析を崩さない）。
    shlex で読めないコマンドは空（止めない側に倒す。PR の本文にあり得る記号で誤爆させない）。"""
    command = HEREDOC_RE.sub(r"\1", command)
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return []
    cmds, cur = [], []
    for t in toks:
        if t and set(t) <= set(";&|"):
            cmds.append(cur)
            cur = []
        else:
            cur.append(t)
    cmds.append(cur)
    out = []
    for c in cmds:
        i = 0
        while i < len(c) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", c[i]):
            i += 1
        if i < len(c) and os.path.basename(c[i]) == "gh":
            out.append(c[i + 1:])
    return out


# 値を取る gh のオプション（読み飛ばすため。必要なものだけ値を拾う）
_VALUE_OPTS = {
    "-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--title", "-H", "--head", "-B", "--base",
    "-T", "--template", "-a", "--assignee", "-l", "--label", "-m", "--milestone", "-p", "--project",
    "-r", "--reviewer", "--recover", "-A", "--author-email", "--subject", "--match-head-commit",
    "--add-label", "--remove-label", "--add-assignee", "--remove-assignee", "--add-project",
    "--remove-project", "--attach",
}


def parse_args(args):
    """(positional, opts)。opts は最後の値（`--x=v` 形も）。"""
    pos, opts, i = [], {}, 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a.startswith("--") and "=" in a:
            k, v = a.split("=", 1)
            opts[k] = v
        elif a in _VALUE_OPTS:
            opts[a] = args[i + 1] if i + 1 < len(args) else ""
            i += 1
        elif a.startswith("-") and len(a) > 2 and a[:2] in _VALUE_OPTS and not a.startswith("--"):
            opts[a[:2]] = a[2:]  # -Ro/r の形
        elif a.startswith("-") and len(a) > 1:
            opts[a] = True
        else:
            pos.append(a)
        i += 1
    return pos, opts


def opt(opts, *names):
    for n in names:
        if n in opts and opts[n] is not True:
            return opts[n]
    return None


def read_file(path, cwd):
    if not path or path == "-":
        return None
    p = path if os.path.isabs(path) else os.path.join(cwd or ".", path)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def gh_body(opts, cwd, command=""):
    """gh に渡した本文。確かめられない渡し方（変数・標準入力・--fill など）は None。"""
    b = opt(opts, "-b", "--body")
    if b is not None:
        if "<<" in b and "<<" in command:
            return command  # --body "$(cat <<'EOF' … EOF)"。本文はコマンドの中のヒアドキュメント
        # "$BODY" のような変数だけの本文は中身が分からない
        return None if re.fullmatch(r"\s*\$\{?\w+\}?\s*", b) else b
    f = opt(opts, "-F", "--body-file")
    if f == "-" and "<<" in command:
        return command  # `-F - <<'EOF'` のヒアドキュメント。本文はコマンドの中にある
    return read_file(f, cwd)


def gh_calls(command, cwd):
    """[(kind, info)] kind ∈ pr_create / pr_merge / issue_edit / issue_view"""
    out = []
    for args in gh_commands(command):
        pos, opts = parse_args(args)
        if len(pos) < 2:
            continue
        repo = opt(opts, "-R", "--repo") or os.environ.get("GH_REPO") or None
        if pos[0] == "pr" and pos[1] == "create":
            out.append(("pr_create", {"repo": repo or repo_from_cwd(cwd), "body": gh_body(opts, cwd, command),
                                      "head": opt(opts, "-H", "--head") or branch_from_cwd(cwd)}))
        elif pos[0] == "pr" and pos[1] == "merge":
            out.append(("pr_merge", {"repo": repo, "selector": pos[2] if len(pos) > 2 else None}))
        elif pos[0] == "issue" and pos[1] in ("edit", "view") and len(pos) > 2:
            sel = pos[2]
            um = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)", sel)
            if um:
                ref = f"{um.group(1)}#{um.group(2)}".lower()
            else:
                nm = re.fullmatch(r"#?(\d+)", sel)
                r = repo or repo_from_cwd(cwd)
                ref = f"{r}#{nm.group(1)}".lower() if (nm and r) else None
            if ref:
                out.append(("issue_" + pos[1], {"ref": ref, "body": gh_body(opts, cwd, command)}))
    return out


def merge_ref_from_gh(info, st_prs, cwd):
    sel = info.get("selector")
    um = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)(?:[/?#].*)?", sel or "")
    if um:
        return f"{um.group(1)}#{um.group(2)}".lower()
    repo = info.get("repo") or repo_from_cwd(cwd)
    nm = re.fullmatch(r"#?(\d+)", sel or "")
    if nm:
        return f"{repo}#{nm.group(1)}".lower() if repo else None
    head = sel or branch_from_cwd(cwd)
    for ref, pr in st_prs.items():
        if head and pr.get("head") == head and (not repo or ref.startswith(repo.lower() + "#")):
            return ref
    return None


def base(tool_name):
    return tool_name.rsplit("__", 1)[-1] if tool_name.startswith("mcp__") else tool_name


# ------------------------------------------------------------------ outputs
def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def inject(context):
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}


def emit(obj):
    if obj:
        print(json.dumps(obj, ensure_ascii=False))


NEXT_STEP = (f"{TAG} PR を作った。次はレビューと CI を待つ（dev-flow の 5 段・手順は pr-review-wait）。"
             "クラウドのセッションは PR イベントの購読（subscribe_pr_activity）、ローカルは Monitor を立てる。"
             "マージの前に Closes 先の issue の body に `## 結果` を書く。")


# ------------------------------------------------------------------- events
def pre_create_check(body):
    if body is None:
        return deny(f"{TAG} PR の本文を確かめられない。本文は --body か --body-file で渡す"
                    "（--fill・--editor・--web・変数・ヒアドキュメント以外の標準入力では確かめられない）。")
    missing = body_missing(body)
    if missing:
        return deny(f"{TAG} PR 本文に次の欄が無い（dev-flow の 4 段）:\n- " + "\n- ".join(missing)
                    + "\n書き足してから作り直す。")
    return None


def pre_merge_check(ref, st):
    pr = st["prs"].get(ref)
    if not pr:
        return None  # 別セッションの PR は分からない。PostToolUse で一言返す
    missing = [i for i in pr.get("closes", []) if i not in st["results"]]
    if not missing:
        return None
    return deny(f"{TAG} {ref} は {', '.join(missing)} を Closes するが、このセッションでは"
                " その issue の body に `## 結果` を書いた・確かめた記録が無い（dev-flow の 7 段）。"
                "マージで自動 close されると記録の無い close になる。issue_read で今の body を取り、"
                "末尾に `## 結果` を足して issue_write（update）で書いてからマージする。"
                "すでに書いてあるなら issue_read で読み直せば通る。")


def on_pre_tool_use(inp):
    tn = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    cwd = inp.get("cwd")
    b = base(tn)
    if tn.startswith("mcp__") and b == "create_pull_request":
        return pre_create_check(ti.get("body") or "")
    if tn.startswith("mcp__") and b in ("merge_pull_request", "enable_pr_auto_merge"):
        o, r, n = ti.get("owner"), ti.get("repo"), ti.get("pullNumber") or ti.get("pull_number")
        if not (o and r and n):
            return None
        return pre_merge_check(f"{o}/{r}#{int(n)}".lower(), read_state(inp["session_id"]))
    if tn == "Bash":
        cmd = ti.get("command", "")
        if not re.search(r"\bgh\b", cmd):
            return None
        st = None
        for kind, info in gh_calls(cmd, cwd):
            if kind == "pr_create":
                res = pre_create_check(info["body"])
                if res:
                    return res
            elif kind == "pr_merge":
                st = st or read_state(inp["session_id"])
                ref = merge_ref_from_gh(info, st["prs"], cwd)
                res = pre_merge_check(ref, st) if ref else None
                if res:
                    return res
    return None


def record_pr(st, ref, body, head):
    repo = ref.split("#", 1)[0]
    st.d["prs"][ref] = {"closes": closes_of(body, repo), "head": head, "created_at": now(),
                        "wait_started": False, "nagged": False}


def on_post_tool_use(inp):
    tn = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    tr = inp.get("tool_response")
    cwd = inp.get("cwd")
    b = base(tn)
    sid = inp["session_id"]

    if tn == "Monitor" or (tn.startswith("mcp__") and b == "subscribe_pr_activity"):
        if os.path.exists(_path(sid)):
            with State(sid) as st:
                for pr in st.d["prs"].values():
                    pr["wait_started"] = True
        return None

    if tn.startswith("mcp__") and b == "create_pull_request":
        m = PR_URL_RE.search(text_of(tr))
        if not m:
            return None
        with State(sid) as st:
            record_pr(st, f"{m.group(1)}#{m.group(2)}".lower(), ti.get("body") or "", ti.get("head"))
        return inject(NEXT_STEP)

    if tn.startswith("mcp__") and b in ("issue_write", "issue_read"):
        o, r, n = ti.get("owner"), ti.get("repo"), ti.get("issue_number")
        if not (o and r and n):
            return None
        if b == "issue_write":
            text = (ti.get("body") or "") if ti.get("method") == "update" else ""
        else:
            text = text_of(tr) if ti.get("method", "get") == "get" else ""
        if RESULT_RE.search(text):
            with State(sid) as st:
                ref = f"{o}/{r}#{int(n)}".lower()
                if ref not in st.d["results"]:
                    st.d["results"].append(ref)
        return None

    if tn.startswith("mcp__") and b in ("merge_pull_request", "enable_pr_auto_merge"):
        o, r, n = ti.get("owner"), ti.get("repo"), ti.get("pullNumber") or ti.get("pull_number")
        if o and r and n and f"{o}/{r}#{int(n)}".lower() not in read_state(sid)["prs"]:
            return inject(f"{TAG} このセッションで作っていない PR をマージした。Closes 先の issue に"
                          " `## 結果` があるか確かめ、無ければ書く（dev-flow の 7 段）。")
        return None

    if tn == "Bash":
        cmd = ti.get("command", "")
        if not re.search(r"\bgh\b", cmd) or failed(tr):
            return None
        out = None
        for kind, info in gh_calls(cmd, cwd):
            if kind == "pr_create":
                m = PR_URL_RE.search(text_of(tr))
                if m:
                    with State(sid) as st:
                        record_pr(st, f"{m.group(1)}#{m.group(2)}".lower(), info["body"] or "", info["head"])
                    out = inject(NEXT_STEP)
            elif kind in ("issue_edit", "issue_view"):
                text = info["body"] if kind == "issue_edit" else text_of(tr)
                if text and RESULT_RE.search(text):
                    with State(sid) as st:
                        if info["ref"] not in st.d["results"]:
                            st.d["results"].append(info["ref"])
            elif kind == "pr_merge":
                st = read_state(sid)
                ref = merge_ref_from_gh(info, st["prs"], cwd)
                if not ref or ref not in st["prs"]:
                    out = inject(f"{TAG} このセッションで作っていない PR をマージした。Closes 先の issue に"
                                 " `## 結果` があるか確かめ、無ければ書く（dev-flow の 7 段）。")
        return out
    return None


def on_stop(inp):
    if inp.get("stop_hook_active"):
        return None
    sid = inp["session_id"]
    if not os.path.exists(_path(sid)):
        return None
    due = []
    with State(sid) as st:
        for ref, pr in st.d["prs"].items():
            if not pr.get("wait_started") and not pr.get("nagged"):
                pr["nagged"] = True
                due.append(ref)
    if not due:
        return None
    reason = (f"{TAG} {', '.join(due)} を作ったが、レビューと CI の待ちを始めていない（dev-flow の 5 段）。"
              "クラウドのセッションは subscribe_pr_activity で PR イベントを購読してからターンを終える。"
              "ローカルは pr-review-wait の手順で Monitor を立てる。"
              "待たない理由（ユーザーが不要と言った等）があるなら、それを返答に書いて終えてよい（この PR では二度と止めない）。")
    return {"decision": "block", "reason": reason}


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    ev = inp.get("hook_event_name", "")
    if not inp.get("session_id"):
        return
    try:
        if ev == "PreToolUse":
            emit(on_pre_tool_use(inp))
        elif ev == "PostToolUse":
            emit(on_post_tool_use(inp))
        elif ev == "Stop":
            emit(on_stop(inp))
        elif ev == "SessionStart":
            gc()
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
