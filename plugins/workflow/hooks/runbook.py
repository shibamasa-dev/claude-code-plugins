#!/usr/bin/env python3
"""runbook: computer use / browser use の手順を runbook に残す強制点。

生ログは hook が機械で取り、手順書（runbook.md）は作業の最後に Claude が書く。書き忘れは Stop で止める。
  - PostToolUse  (hook-post)          : 対象ツールの呼び出しを <root>/_inbox/<sid>.jsonl へ追記（batch は 1 アクション 1 行に展開）。
                                        残すのはホワイトリストのキーだけで、それ以外の文字列・数値は文字数だけ残す
                                        （type の text・form_input の value・javascript のコード・パスワードは 1 文字も残さない）
  - Stop         (hook-stop)          : inbox に操作ステップが OP_MIN 件以上あり、new/use/dismiss で仕上げていなければ
                                        K_STOPS 回ごとに block（仕上げるまでの 1 まとまりにつき最大 MAX_NAGS 回）
  - SessionStart (hook-session-start) : 1 日 1 回だけ sweep --apply。何か消したときだけ 1 行出す
保存先 <root> = $RUNBOOK_ROOT or ~/.claude/runbooks
  _inbox/<sid>.jsonl   仕上げ前の生ログ（hook は作業名を知らない）
  _state/<sid>.json    Stop の nag カウンタと仕上げ記録
  <YYYY-MM-DD>_<slug>/ runbook.md ＋ steps.jsonl（2 回目以降の実行分は steps-<日付>.jsonl）
何が起きても hook は例外で落ちず exit 0（Stop の block だけが唯一の「止める」出力）。

CLI（Claude が実行する）:
  new --session <id> --slug <作業名> --recurrence once|monthly|yearly [--title ...] [--gif <path>]
  use <dir> --session <id>
  dismiss --session <id> --why "..."
  promote <dir> --skill <スキルのディレクトリ>
  sweep [--apply]
  list
"""
import argparse, fcntl, json, os, re, shutil, subprocess, sys, time
from datetime import date, datetime, timedelta

ROOT = os.path.expanduser(os.environ.get("RUNBOOK_ROOT") or "~/.claude/runbooks")
INBOX = os.path.join(ROOT, "_inbox")
STATE_DIR = os.path.join(ROOT, "_state")
SELF = "runbook"
K_STOPS = 3            # 操作が OP_MIN 件に達してから（前回 nag から）この回数 Stop が来たら block
MAX_NAGS = 3           # 仕上げるまでの 1 まとまりにつき block の上限（new/use/dismiss でリセット）
OP_MIN = 3             # これ未満の操作しかないセッションは止めない
INBOX_GC_DAYS = 14     # 仕上げられないまま放置された inbox ログ
STATE_GC_DAYS = 30
GIF_MV_TIMEOUT = 10    # ~/Downloads はこのホストで読み書きがハングすることがある
KEEP_DAYS = {"once": ("created", 60), "monthly": ("last_used", 45), "yearly": ("last_used", 400)}
FM_KEYS = ["title", "created", "last_used", "uses", "recurrence", "keep_until", "status", "sessions", "gif"]
DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_.+")
SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
TOOL_RE = re.compile(r"^mcp__(claude-in-chrome|computer-use|remote-devices|Claude_Browser)__")  # Playwright は対象外

# ------------------------------------------------------------ step 記録
# 残してよいキー（値はそのまま）。これ以外は文字列・数値なら文字数だけ、IGNORE は捨てる
KEEP = {"action", "ref", "ref_id", "element_index", "query", "label", "app", "window_id", "filter",
        "coordinate", "start_coordinate", "to_coordinate", "region", "scroll_direction"}
IGNORE = {"tabId", "tabIds", "serverId", "deviceId", "scale", "duration", "scroll_amount", "repeat", "max_chars",
          "depth", "limit", "save_to_disk", "force", "width", "height", "preset", "colorScheme", "count", "dx", "dy",
          "foreground", "onlyErrors", "createIfEmpty", "pattern", "urlPattern", "requestId", "lines", "options", "download"}
# 分類（判断はここ 1 箇所）: 画面・状態を変えうるものが「操作」、それ以外は「読み取り」
OP_ACTIONS = {"left_click", "right_click", "middle_click", "double_click", "triple_click", "click", "type", "key",
              "scroll", "left_click_drag", "drag", "left_mouse_down", "left_mouse_up"}
OP_TOOLS = {"navigate", "form_input", "file_upload", "upload_image", "javascript_tool", "shortcuts_execute",
            "autofill_credential", "open_application", "app_click", "app_scroll", "write_clipboard"}
SHOT = {"screenshot", "zoom", "app_screenshot", "app_zoom"}

def now(): return datetime.now().isoformat(timespec="seconds")
def today(): return date.today()
def valid_sid(s): return isinstance(s, str) and bool(SID_RE.match(s))
def inbox_path(sid): return os.path.join(INBOX, f"{sid}.jsonl")

def clean_url(u):
    """クエリ文字列・フラグメント・userinfo を落とす。javascript:/data: は中身を捨てる。"""
    if not isinstance(u, str): return None
    s = u.strip()
    m = re.match(r"(?i)^(javascript|data):", s)
    if m: return f"{m.group(0)}<{len(s)}文字>"
    s = re.sub(r"^([A-Za-z][A-Za-z0-9+.-]*://)?[^/@]*@", r"\1", s)
    return s.split("#", 1)[0].split("?", 1)[0]

def _plain(v):
    return isinstance(v, (str, int, float, bool)) or (isinstance(v, list) and all(isinstance(x, (int, float)) for x in v))

def _step(tool, base, ti, sub=None, app=None):
    act = ti.get("action") if isinstance(ti.get("action"), str) else None
    st = {"t": now(), "tool": tool}
    if sub: st["sub"] = sub
    if act: st["action"] = act
    if app and "app" not in ti: st["app"] = app
    masked = {}
    for k, v in ti.items():
        if k == "action" or k in IGNORE: continue
        if k == "url":
            cu = clean_url(v)
            if cu is not None: st["url"] = cu
        elif base == "app_menu" and k in ("path", "list") and isinstance(v, (str, list)):
            st["label"] = " > ".join(map(str, v)) if isinstance(v, list) else v
        elif k in KEEP and _plain(v):
            st[k] = v
        elif isinstance(v, (str, int, float, bool)):
            masked[k] = len(str(v))
        elif isinstance(v, (dict, list)):
            masked[k] = len(json.dumps(v, ensure_ascii=False))
    if masked: st["masked"] = masked
    st["kind"] = "op" if (act in OP_ACTIONS or base in OP_TOOLS or (base == "app_menu" and "path" in ti)) else "read"
    st["shot"] = bool(act in SHOT or base in SHOT or ti.get("save_to_disk") is True)
    return st

def steps_from(tool, ti):
    base = tool.rsplit("__", 1)[-1]
    acts = ti.get("actions")
    if not isinstance(acts, list):
        return [_step(tool, base, ti)]
    app = ti.get("app") if isinstance(ti.get("app"), str) else None
    out = []
    for a in acts:
        if not isinstance(a, dict): continue
        if isinstance(a.get("name"), str) and isinstance(a.get("input"), dict):   # browser_batch: {name, input}
            out.append(_step(tool, a["name"].rsplit("__", 1)[-1], a["input"], sub=a["name"], app=app))
        else:                                                                     # computer_batch / app_batch: フラット
            out.append(_step(tool, base, a, app=app))
    return out

def count_steps(path):
    n_all = n_op = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try: d = json.loads(line)
                except Exception: continue
                if isinstance(d, dict): n_all += 1; n_op += d.get("kind") == "op"
    except FileNotFoundError:
        pass
    return n_all, n_op

# ---------------------------------------------------------------- state io
class State:
    """flock 付き read-modify-write。並列の hook / CLI が同時に来ても壊れない。"""
    def __init__(self, sid):
        os.makedirs(STATE_DIR, exist_ok=True)
        self.p = os.path.join(STATE_DIR, f"{sid}.json"); self.lock = self.p + ".lock"
    def __enter__(self):
        self.lf = open(self.lock, "w"); fcntl.flock(self.lf, fcntl.LOCK_EX)
        try:
            with open(self.p) as f: self.d = json.load(f)
        except Exception:
            self.d = {}
        self.d.setdefault("stops_since", 0); self.d.setdefault("nags", 0); self.d.setdefault("log", [])
        return self
    def __exit__(self, *a):
        tmp = self.p + ".tmp"
        with open(tmp, "w") as f: json.dump(self.d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.p)
        fcntl.flock(self.lf, fcntl.LOCK_UN); self.lf.close()

def finalize(sid, rec):
    """new/use/dismiss の共通後処理: nag カウンタを戻し、何をしたかを残す。"""
    with State(sid) as st:
        st.d["stops_since"] = 0; st.d["nags"] = 0
        st.d["log"].append(dict(rec, at=now()))

# ------------------------------------------------------------- frontmatter
def read_fm(path):
    try:
        with open(path, encoding="utf-8") as f: text = f.read()
    except Exception:
        return None, None
    m = re.match(r"^---\n(.*?)\n---\n?", text, re.S)
    if not m: return None, None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line: continue
        k, v = line.split(":", 1); k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'": v = v[1:-1]
        elif v.startswith("[") and v.endswith("]"): v = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
        elif v in ("", "null", "~"): v = None
        fm[k] = v
    return fm, text[m.end():]

def dump_fm(fm):
    lines = ["---"]
    for k in FM_KEYS:
        v = fm.get(k)
        if isinstance(v, list): s = "[" + ", ".join(v) + "]"
        elif v is None: s = "null"
        elif k in ("title", "gif"): s = '"' + str(v).replace("\n", " ") + '"'
        else: s = str(v)
        lines.append(f"{k}: {s}")
    return "\n".join(lines + ["---"]) + "\n"

def write_runbook(path, fm, body):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(dump_fm(fm) + body)
    os.replace(tmp, path)

def pdate(s):
    try: return date.fromisoformat(str(s))
    except Exception: return None

def calc_keep(fm):
    key, days = KEEP_DAYS[fm["recurrence"]]
    return ((pdate(fm.get(key)) or today()) + timedelta(days=days)).isoformat()

BODY = """
# {title}

## 目的

## 前提・入力値（秘密は書かない。パスワード・暗証番号・取引パスワードは『ユーザーが入力』とだけ書く）

## 手順（画面名・ボタンの文言・入れた値。座標は書かない）

## 分岐・つまずき

## 止める地点（承認境界：決済・送信・確定の直前など）

## 検証（完了をどこで確かめたか）

## 録画

{rec}
"""

# ------------------------------------------------------------------ events
def on_post(inp):
    tool = inp.get("tool_name")
    sid = inp.get("session_id")
    if not isinstance(tool, str) or not TOOL_RE.match(tool) or not valid_sid(sid): return
    ti = inp.get("tool_input")
    steps = steps_from(tool, ti if isinstance(ti, dict) else {})
    if not steps: return
    os.makedirs(INBOX, exist_ok=True)
    with open(inbox_path(sid), "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in steps))
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)

def on_stop(inp):
    if inp.get("stop_hook_active"): return
    sid = inp.get("session_id")
    if not valid_sid(sid) or not os.path.exists(inbox_path(sid)): return  # ブラウザを触っていないセッションに状態を作らない
    n_all, n_op = count_steps(inbox_path(sid))
    if n_op < OP_MIN: return
    with State(sid) as st:
        st.d["stops_since"] += 1
        if st.d["stops_since"] < K_STOPS or st.d["nags"] >= MAX_NAGS: return
        st.d["stops_since"] = 0; st.d["nags"] += 1
    reason = "\n".join([
        f"[runbook] このセッションで computer use / browser use の操作を {n_op} 件した"
        f"（ログ {n_all} 件は自動記録済み・入力値は伏せてある）が、まだ runbook に仕上げていない。次のどれかを実行してから終了する:",
        f"  新規の手順:          {SELF} new --session {sid} --slug <作業名> --recurrence once|monthly|yearly --title \"<タイトル>\" [--gif <録画GIFのパス>]",
        f"  既存 runbook の再実行: {SELF} use <フォルダ（{SELF} list で探す）> --session {sid}",
        f"  記録不要（検証だけ等）: {SELF} dismiss --session {sid} --why \"<理由>\"",
        "new / use の後は runbook.md の各見出しを steps.jsonl と会話から埋める（パスワード・暗証番号は『ユーザーが入力』とだけ書く）。"])
    print(json.dumps({"decision": "block", "reason": reason,
                      "hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": reason}}, ensure_ascii=False))

def on_session_start(inp):
    """1 日 1 回だけ掃除する（1 日に何十セッションも起動するので、掃除と報告は最初の 1 回だけ）。"""
    os.makedirs(ROOT, exist_ok=True)
    with open(os.path.join(ROOT, ".sweep.lock"), "w") as lf:
        try: fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError: return   # 同時に起動した別セッションが掃除中
        marker = os.path.join(ROOT, ".last_sweep")
        try:
            with open(marker) as f: last = f.read().strip()
        except Exception:
            last = ""
        if last == today().isoformat(): return
        with open(marker, "w") as f: f.write(today().isoformat())  # 先に書く（掃除が落ちても毎セッション再試行しない）
        rb, ib, _ = sweep(apply=True)
    parts = []
    if rb: parts.append(f"期限切れ {len(rb)}件を削除（{', '.join(rb[:3])}{', …' if len(rb) > 3 else ''}）")
    if ib: parts.append(f"仕上げられなかった inbox ログ {len(ib)}件を削除")
    if parts: print("runbooks: " + "／".join(parts))

# ------------------------------------------------------------------- sweep
def sweep(apply):
    """(消す runbook, 消す inbox, 消す state) を返す。apply のときだけ実際に消す。"""
    rb, ib, stf = [], [], []
    t = today()
    try: names = sorted(os.listdir(ROOT))
    except FileNotFoundError: names = []
    for n in names:
        d = os.path.join(ROOT, n)
        if not DIR_RE.match(n) or os.path.islink(d) or not os.path.isdir(d): continue
        fm, _ = read_fm(os.path.join(d, "runbook.md"))
        ku = pdate(fm.get("keep_until")) if fm else None
        if fm and fm.get("status") == "draft" and ku and ku < t:   # 読めないもの・draft 以外は残す
            rb.append(n)
    for dirpath, days, out in ((INBOX, INBOX_GC_DAYS, ib), (STATE_DIR, STATE_GC_DAYS, stf)):
        cutoff = time.time() - days * 86400
        try:
            for n in sorted(os.listdir(dirpath)):
                fp = os.path.join(dirpath, n)
                if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff: out.append(n)
        except FileNotFoundError:
            pass
    if apply:
        for n in rb: shutil.rmtree(os.path.join(ROOT, n), ignore_errors=True)
        for dirpath, out in ((INBOX, ib), (STATE_DIR, stf)):
            for n in out:
                try: os.remove(os.path.join(dirpath, n))
                except Exception: pass
    return rb, ib, stf

# --------------------------------------------------------------------- cli
def err(msg):
    print(msg, file=sys.stderr); return 1

def resolve_dir(arg):
    """root 直下の <YYYY-MM-DD>_<slug> で runbook.md を持つものだけ受け付ける（誤って他の場所を消さない）。"""
    p = os.path.expanduser(arg)
    if not os.path.isabs(p): p = os.path.join(ROOT, p)
    p = os.path.realpath(p)
    if os.path.dirname(p) != os.path.realpath(ROOT) or not DIR_RE.match(os.path.basename(p)): return None
    return p if os.path.isfile(os.path.join(p, "runbook.md")) else None

def move_inbox(sid, dst):
    """今回の inbox を dst へ移す（既にあれば追記）。(全件, 操作) を返す。inbox が無ければ (0, 0)。"""
    src = inbox_path(sid)
    if not os.path.exists(src): return 0, 0
    n = count_steps(src)
    if os.path.exists(dst):
        with open(src, encoding="utf-8") as s, open(dst, "a", encoding="utf-8") as d: d.write(s.read())
        os.remove(src)
    else:
        os.replace(src, dst)
    return n

def move_gif(src, d):
    """GIF を runbook フォルダへ mv する。ハング・失敗したら元のパスを返す（in-process で stat もしない）。"""
    src = os.path.abspath(os.path.expanduser(src))
    try:
        p = subprocess.Popen(["mv", src, d + "/"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return src, f"mv を起動できない: {e}"
    try:
        rc = p.wait(timeout=GIF_MV_TIMEOUT)
    except subprocess.TimeoutExpired:
        p.kill()
        try: p.wait(timeout=2)
        except Exception: pass
        return src, f"mv が {GIF_MV_TIMEOUT} 秒で終わらない"
    if rc != 0: return src, f"mv が失敗（exit {rc}）"
    return os.path.join(d, os.path.basename(src)), None

def cli_new(a):
    if not valid_sid(a.session): return err("--session が不正")
    slug = re.sub(r"[\s/\\:]+", "-", a.slug).strip("-.")
    if not slug: return err("--slug が空")
    t = today().isoformat()
    d = os.path.join(ROOT, f"{t}_{slug}")
    if os.path.exists(d): return err(f"{d} は既にある。同じ作業の再実行なら use を使う")
    os.makedirs(d)
    n_all, n_op = move_inbox(a.session, os.path.join(d, "steps.jsonl"))
    if not n_all: open(os.path.join(d, "steps.jsonl"), "a").close()
    gif, gif_err = move_gif(a.gif, d) if a.gif else (None, None)
    title = a.title or slug
    fm = {"title": title, "created": t, "last_used": t, "uses": 1, "recurrence": a.recurrence,
          "keep_until": None, "status": "draft", "sessions": [a.session], "gif": gif}
    fm["keep_until"] = calc_keep(fm)
    rec = ("- なし（computer use には録画機能が無い。要所だけ手順に書く）" if not gif else
           f"- GIF（移動できず元の場所のまま）: {gif}" if gif_err else f"- GIF: {gif}")
    write_runbook(os.path.join(d, "runbook.md"), fm, BODY.format(title=title, rec=rec + "\n- 生ログ: steps.jsonl（入力値は伏せてある）"))
    finalize(a.session, {"how": "new", "dir": d, "steps": n_all})
    print(d)
    print(f"  steps.jsonl: {n_all} 件（操作 {n_op}）／ keep_until: {fm['keep_until']}（{a.recurrence}）")
    if not n_all: print("  ⚠️ このセッションの inbox が無かった（steps.jsonl は空）")
    if gif_err: print(f"  ⚠️ GIF を移せなかった（{gif_err}）。元のパスを frontmatter の gif: に記録した")
    print("次: runbook.md の各見出しを steps.jsonl と会話から埋める（パスワード・暗証番号は『ユーザーが入力』とだけ書く）")
    return 0

def cli_use(a):
    if not valid_sid(a.session): return err("--session が不正")
    d = resolve_dir(a.dir)
    if not d: return err(f"{a.dir} は runbook のフォルダではない（{SELF} list で探す）")
    rb = os.path.join(d, "runbook.md")
    fm, body = read_fm(rb)
    if not fm or fm.get("recurrence") not in KEEP_DAYS: return err(f"{rb} の frontmatter が読めない")
    t = today().isoformat()
    n_all, n_op = move_inbox(a.session, os.path.join(d, f"steps-{t}.jsonl"))
    try: fm["uses"] = int(fm.get("uses") or 1) + 1
    except ValueError: fm["uses"] = 2
    fm["last_used"] = t
    ss = fm.get("sessions")
    ss = ss if isinstance(ss, list) else ([ss] if ss else [])
    fm["sessions"] = [s for s in ss if s != a.session] + [a.session]
    old = pdate(fm.get("keep_until"))
    new = calc_keep(fm)
    fm["keep_until"] = max(old.isoformat(), new) if old else new
    write_runbook(rb, fm, body)
    finalize(a.session, {"how": "use", "dir": d, "steps": n_all})
    print(d)
    print(f"  steps-{t}.jsonl: {n_all} 件（操作 {n_op}）／ uses: {fm['uses']} ／ keep_until: {fm['keep_until']}")
    if not n_all: print("  ⚠️ このセッションの inbox が無かった（今回分のログなし）")
    if fm["uses"] >= 2:
        print(f"{fm['uses']}回目の実行。スキル化を提案する（skill-creator に runbook.md を渡す）")
    return 0

def cli_dismiss(a):
    if not valid_sid(a.session): return err("--session が不正")
    if not a.why.strip(): return err("--why に理由を書く")
    n_all, _ = count_steps(inbox_path(a.session))
    try: os.remove(inbox_path(a.session))
    except FileNotFoundError: pass
    finalize(a.session, {"how": "dismiss", "why": a.why, "steps": n_all})
    print(f"dismissed: {n_all} 件のログを捨てた（理由: {a.why}）")
    return 0

def cli_promote(a):
    d = resolve_dir(a.dir)
    if not d: return err(f"{a.dir} は runbook のフォルダではない。何も消していない")
    skill = os.path.realpath(os.path.expanduser(a.skill))
    if not os.path.isfile(os.path.join(skill, "SKILL.md")): return err(f"{skill}/SKILL.md が無い。何も消していない")
    if skill == d or skill.startswith(d + os.sep): return err("スキルが runbook フォルダの中にある。何も消していない")
    shutil.rmtree(d)
    print(f"promoted: {os.path.basename(d)} を削除した（以降の正本は {skill}）")
    return 0

def cli_sweep(a):
    rb, ib, stf = sweep(apply=a.apply)
    tag = "削除した" if a.apply else "[dry-run] 削除対象"
    print(f"{tag}: 期限切れ draft {len(rb)} 件／仕上げられていない inbox（{INBOX_GC_DAYS}日超）{len(ib)} 件／古い状態ファイル {len(stf)} 件")
    for n in rb: print(f"  runbook  {n}")
    for n in ib: print(f"  inbox    {n}")
    if not a.apply and (rb or ib or stf): print("--apply で削除する")
    return 0

def cli_list(a):
    rows = []
    try: names = sorted(os.listdir(ROOT))
    except FileNotFoundError: names = []
    for n in names:
        if not DIR_RE.match(n) or not os.path.isdir(os.path.join(ROOT, n)): continue
        fm, _ = read_fm(os.path.join(ROOT, n, "runbook.md"))
        if not fm: rows.append((n, "(frontmatter が読めない)", "-", "-", "-", "-")); continue
        rows.append((n, fm.get("title") or "", fm.get("status") or "-", str(fm.get("uses") or "-"),
                     fm.get("last_used") or "-", fm.get("keep_until") or "-"))
    if not rows: print("runbook なし")
    for n, title, status, uses, last, keep in rows:
        print(f"{n}\n    {title}  status={status} uses={uses} last_used={last} keep_until={keep}")
    try: pend = [x for x in os.listdir(INBOX) if x.endswith(".jsonl")]
    except FileNotFoundError: pend = []
    if pend: print(f"(未仕上げの inbox: {len(pend)} セッション)")
    return 0

def cli(argv):
    ap = argparse.ArgumentParser(prog="runbook.py")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new"); p.add_argument("--session", required=True); p.add_argument("--slug", required=True)
    p.add_argument("--recurrence", required=True, choices=list(KEEP_DAYS)); p.add_argument("--title"); p.add_argument("--gif")
    p.set_defaults(fn=cli_new)
    p = sp.add_parser("use"); p.add_argument("dir"); p.add_argument("--session", required=True); p.set_defaults(fn=cli_use)
    p = sp.add_parser("dismiss"); p.add_argument("--session", required=True); p.add_argument("--why", required=True)
    p.set_defaults(fn=cli_dismiss)
    p = sp.add_parser("promote"); p.add_argument("dir"); p.add_argument("--skill", required=True); p.set_defaults(fn=cli_promote)
    p = sp.add_parser("sweep"); p.add_argument("--apply", action="store_true"); p.set_defaults(fn=cli_sweep)
    p = sp.add_parser("list"); p.set_defaults(fn=cli_list)
    a = ap.parse_args(argv)
    return a.fn(a)

HOOKS = {"hook-post": on_post, "hook-stop": on_stop, "hook-session-start": on_session_start}

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in HOOKS:
        sys.exit(cli(sys.argv[1:]))
    try:
        inp = json.load(sys.stdin)
    except Exception:
        inp = None
    if isinstance(inp, dict) or cmd == "hook-session-start":
        try:
            HOOKS[cmd](inp if isinstance(inp, dict) else {})
        except Exception as e:  # hook は絶対に落とさない
            print(f"runbook: {e}", file=sys.stderr)
    sys.exit(0)

if __name__ == "__main__":
    main()
