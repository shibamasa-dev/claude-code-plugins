#!/usr/bin/env python3
"""PostToolUse hook: マージの後、手元のマージ先ブランチを origin に追従させる汎用ディスパッチャ。

なぜ PostToolUse か:
  PreToolUse でも permissionDecisionReason は Claude のコンテキストに乗るが、**届けるには
  ツールを止めるしかない**（additionalContext フィールドは PostToolUse 以降にしか無い）。
  merge は既に完了していて止める対象が無いので、ここは PostToolUse の additionalContext が正しい。
  逆に「古いブランチの上に commit する」は積む前に止めるべきなので、bash-guard.py(PreToolUse) の
  rule_main_commit_freshness が deny で担当する。**止める係=bash-guard / 知らせる係=本 hook**。

なぜ必要か:
  マージは remote で起きるため、手元のチェックアウトは自動では追従しない。そのチェックアウトを
  直に実行している定期ジョブや常駐プロセスは、pull するまで旧コードを回し続ける。
  「マージすれば有効」ではなく「マージ＋手元の pull で有効」。

ルール追加＝関数を1つ書いて RULES に登録するだけ（hook の追加登録は不要）。
bash-guard.py と同じ RULES 方式に揃えてある。

現行ルール:
  1. post-merge-pull : マージの後、手元で開いているブランチがその PR のマージ先で、origin より
                       遅れていれば --ff-only で追従。clean に通れば実行して報告、通らなければ
                       **触らず**状況だけ注入。マージ先はブランチ名を決め打ちせずに決める:
                       - GitHub コネクタ（mcp__*__merge_pull_request）: 結果の merge commit の SHA が
                         手元のブランチの origin に入ったか。cwd の origin がマージした owner/repo と
                         同じときだけ動く（別リポの PR をマージしただけで手元を動かさない）
                       - gh pr merge: `gh pr view` の baseRefName。取れなければリポの既定ブランチ
                       - git merge: リポの既定ブランチ（origin/HEAD）

設計上の約束:
  - **自動 stash はしない。** stash pop の競合で作業を黙って壊すため。ff-only が拒否したら
    状況（behind 数・未コミット変更ファイル）を注入して判断を Claude/ユーザーに返す。
  - **問題が無いときは完全に silent**（exit 0・出力なし）。毎 Bash コールで走るため。
  - 判定は git の状態を直接見る（コネクタの結果は merge commit の SHA だけを使う）。
"""
import json
import os
import re
import shlex
import subprocess
import sys

_CWD = None
_RESPONSE = None

MERGE_RE = re.compile(r"\b(gh\s+pr\s+merge\b|git\s+merge(?!-)(?!\s+--(abort|continue|quit)))")
COMMIT_RE = re.compile(r"\bgit\s+commit\b")


def inject(context: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": context,
        }
    }


def _git(args, cwd, timeout=15):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def _current_branch(cwd):
    r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return r.stdout.strip() if r.returncode == 0 else None


def _remote_default(cwd):
    """origin が今いう既定ブランチ（ls-remote、読むだけ）。手元の origin/HEAD は fetch で更新されないため先に聞く。
    繋がらない・認証が要るときは None（待たせない）。"""
    try:
        r = subprocess.run(["git", "ls-remote", "--symref", "origin", "HEAD"], cwd=cwd, capture_output=True, stdin=subprocess.DEVNULL,
                           text=True, timeout=5, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (subprocess.TimeoutExpired, OSError):
        return None
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD$", r.stdout, re.M) if r.returncode == 0 else None
    return m.group(1) if m else None


def _default_branch(cwd):
    """リポの既定ブランチ。origin に聞き、繋がらなければ手元の origin/HEAD、それも無ければ origin/main・origin/master の有る方。"""
    name = _remote_default(cwd)
    if name:
        return name
    r = _git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd, timeout=5)
    name = r.stdout.strip() if r.returncode == 0 else ""
    if name.startswith("origin/"):
        return name[len("origin/"):]
    for cand in ("main", "master"):
        if _git(["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{cand}"], cwd, timeout=5).returncode == 0:
            return cand
    return None


def _repo_state(cwd, branch):
    """(behind, dirty_files) を返す。判定不能なら None。"""
    # fetch は best-effort（offline なら素通り＝邪魔しない）
    _git(["fetch", "--quiet", "origin", "--", branch], cwd)
    r = _git(["rev-list", "--count", f"HEAD..origin/{branch}"], cwd)
    if r.returncode != 0:
        return None
    try:
        behind = int(r.stdout.strip() or "0")
    except ValueError:
        return None
    r = _git(["status", "--porcelain"], cwd)
    dirty = [l for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []
    return behind, dirty


def _origin_slug(cwd):
    """origin の owner/repo（小文字）。GitHub でなければ None。"""
    r = _git(["config", "--get", "remote.origin.url"], cwd, timeout=5)
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def _origin_host_slug(cwd):
    """origin の (host, owner/repo)（小文字）。GitHub Enterprise など github.com 以外のホストも読む。"""
    r = _git(["config", "--get", "remote.origin.url"], cwd, timeout=5)
    url = r.stdout.strip() if r.returncode == 0 else ""
    m = (re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url, re.I)
         or re.match(r"^(?:[^@/]+@)?([^/:]+):(.+)$", url))
    if not m:
        return None
    parts = re.sub(r"(?:\.git)?/?$", "", m.group(2)).split("/")
    return (m.group(1).lower(), "/".join(parts[-2:]).lower()) if len(parts) >= 2 else None


def _same_repo(cwd, repo):
    """gh の -R（[HOST/]OWNER/REPO）が cwd の origin と同じリポか。
    HOST 省略時は owner/repo だけで比べる（GitHub Enterprise の clone で `-R O/R` と書いても同じリポとみなす）。"""
    origin = _origin_host_slug(cwd)
    parts = repo.strip().rstrip("/").split("/")
    if not origin or len(parts) not in (2, 3):
        return False
    if len(parts) == 3 and parts[0].lower() != origin[0]:
        return False
    return "/".join(parts[-2:]).lower() == origin[1]


# ------------------------------------------------------------ post-merge-pull
GH_MERGE_RE = re.compile(r"\bgh\s+pr\s+merge\b([^;&|\n]*)")
# gh pr merge で値を取るフラグ（セレクタと取り違えないため）
GH_MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject",
                        "-A", "--author-email", "--match-head-commit"}


def _cwd():
    return _CWD if (_CWD and os.path.isdir(_CWD)) else None


def _gh_merge_target(args: str):
    """gh pr merge の引数から (セレクタ, -R のリポ) を取る。"""
    try:
        toks = shlex.split(args)
    except ValueError:
        return None, None
    sel, repo, i = None, None, 0
    while i < len(toks):
        t = toks[i]
        if t in GH_MERGE_VALUE_FLAGS:
            if t in ("-R", "--repo") and i + 1 < len(toks):
                repo = toks[i + 1]
            i += 2
            continue
        if t.startswith("--repo="):
            repo = t.split("=", 1)[1]
        elif not t.startswith("-") and sel is None:
            sel = t
        i += 1
    if not repo and sel:
        u = re.match(r"^https?://([^/]+)/([^/]+)/([^/]+)/pull/\d+", sel)
        if u:
            repo = "/".join(u.groups())  # URL のセレクタはそのリポを指す
    return sel, repo


def _gh_base(cwd, sel, repo):
    """gh pr view で PR のマージ先ブランチを引く。取れなければ None。"""
    cmd = ["gh", "pr", "view"] + ([sel] if sel else []) + (["-R", repo] if repo else []) \
        + ["--json", "baseRefName", "-q", ".baseRefName"]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return None
    name = r.stdout.strip()
    return name if r.returncode == 0 and name and "\n" not in name else None


def rule_post_merge_pull(command: str):
    m = MERGE_RE.search(command)
    if not m:
        return None
    cwd = _cwd()
    if cwd is None:
        return None
    try:
        g = GH_MERGE_RE.search(command)
        if g:
            sel, repo = _gh_merge_target(g.group(1))
            if repo and not _same_repo(cwd, repo):
                return None  # 別リポの PR をマージしただけ
            base = _gh_base(cwd, sel, repo) or _default_branch(cwd)
        else:
            base = _default_branch(cwd)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return _pull_branch(base)


def _merge_sha(resp):
    """コネクタの結果から merge commit の SHA を探す（JSON 文字列の入れ子も開く）。"""
    if isinstance(resp, str):
        t = resp.strip()
        if t[:1] in "{[":
            try:
                return _merge_sha(json.loads(t))
            except ValueError:
                return None
        return None
    if isinstance(resp, dict):
        v = resp.get("sha")
        if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{40}", v):
            return v
        resp = list(resp.values())
    if isinstance(resp, list):
        for v in resp:
            found = _merge_sha(v)
            if found:
                return found
    return None


def rule_post_merge_pull_mcp(tool_input: dict):
    """コネクタでマージした後。cwd が同じリポで、手元のブランチがマージ先のときだけ追従させる。"""
    owner, repo = tool_input.get("owner"), tool_input.get("repo")
    cwd = _cwd()
    if not (owner and repo and cwd):
        return None
    try:
        if _origin_slug(cwd) != f"{owner}/{repo}".lower():
            return None
        sha = _merge_sha(_RESPONSE)
        if not sha:
            return _pull_branch(_default_branch(cwd))
        branch = _current_branch(cwd)
        if not branch or branch == "HEAD":
            return None
        _git(["fetch", "--quiet", "origin", "--", branch], cwd)
        if _git(["merge-base", "--is-ancestor", sha, f"origin/{branch}"], cwd).returncode != 0:
            return None  # マージ先は手元のブランチではない
    except (subprocess.TimeoutExpired, OSError):
        return None
    return _pull_branch(branch)


def _pull_branch(base):
    """手元で base を開いていて origin/base より遅れていれば --ff-only で追従する。"""
    cwd = _cwd()
    if cwd is None or not base:
        return None
    try:
        if _current_branch(cwd) != base:
            return None  # マージ先以外のブランチに origin/<base> を引き込まない
        state = _repo_state(cwd, base)
        if state is None:
            return None
        behind, dirty = state
        if behind == 0:
            return None  # 既に最新＝silent
        # --ff-only は衝突するローカル変更があれば自ら拒否する（勝手に壊さない）。
        # 自動 stash は絶対にしない: stash pop の競合で作業を黙って壊すため。
        r = _git(["pull", "--ff-only", "origin", base], cwd, timeout=60)
        if r.returncode == 0:
            return inject(
                f"[git-freshness] ローカル {base} を自動 pull しました（{behind} commits 追従）。"
                "このチェックアウトを直に実行しているジョブがあれば、これでマージ済みのコードが動きます。"
            )
        detail = (r.stderr or r.stdout).strip().splitlines()
        detail = detail[-1] if detail else "(理由不明)"
        files = ", ".join(l[3:] for l in dirty[:5]) or "(なし)"
        return inject(
            f"[git-freshness] ⚠️ ローカル {base} が origin/{base} より {behind} commits 遅れていますが、"
            f"自動 pull できませんでした: {detail}\n"
            f"未コミット変更 {len(dirty)} 件: {files}\n"
            "**自動 stash はしていません**（stash pop の競合で作業を壊さないため）。"
            "変更を commit するか stash するか、ユーザーに確認して判断してください。"
            "pull するまで、このチェックアウトは古いコードのままです。"
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


RULES = [rule_post_merge_pull]          # Bash のコマンドを見るルール
MCP_RULES = {"merge_pull_request": rule_post_merge_pull_mcp}  # コネクタのツール名（末尾）→ ルール


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name") or ""
    global _CWD, _RESPONSE
    _CWD = data.get("cwd") or os.getcwd()
    _RESPONSE = data.get("tool_response")
    if tool.startswith("mcp__"):
        rule = MCP_RULES.get(tool.rsplit("__", 1)[-1])
        result = rule(data.get("tool_input") or {}) if rule else None
        if result:
            print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    if tool != "Bash":
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "")
    for rule in RULES:
        result = rule(command)
        if result:
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(0)
    sys.exit(0)


if __name__ == "__main__":
    main()
