#!/usr/bin/env python3
"""PreToolUse hook: Bash コマンドの汎用ガードディスパッチャ。

matcher は "Bash"（ツール名しかマッチできない）なので全 Bash コールで起動し、
コマンド内容のフィルタは本スクリプトの RULES で行う。ルール追加＝関数を1つ
書いて RULES に登録するだけ（hook の追加登録は不要）。

現行ルール:
  1. merge-gate  : git merge / gh pr merge の前にデグレ検証を要求
                   **通過マーカーは無い**(2026-09-23 廃止)。CLAUDE.md が
                   「マージは常にユーザー判断」と定めているため、証跡を積んで Claude に
                   通させる設計自体が方針と食い違う。判断する人に返す。
                   返し方は ask（その場でユーザーに許可の確認を出す。2026-09-24 承認）。
                   ただし permission_mode が bypassPermissions（確認なしで動く spinoff 等）の
                   ときは ask が誰にも見られないので deny。deny は ask より強い（main 参照）。
                   例外は MERGE_ALLOWED_REPOS(guards の設定 merge_allowed_repos に書いたリポ)と、
                   upstream 追いつきマージ(現在のブランチへ origin/<default> か
                   origin/<current> を取り込むもの)。後者は 2 本の in-flight ブランチを
                   合成しないうえ、push-freshness が手順(1)として指示している。
                   **オープン PR が 0 件のリポでは発火しない**(2026-09-23)。
                   ゲートの目的は「複数のオープン PR が絡むマージ」なので守る対象が無い。
                   判定できない(未認証/オフライン)ときは従来どおり deny。
                   fallback はコマンド位置でしか判定しない(文字列リテラル誤爆の修正)。
                   **作用するリポはマージコマンド自身から決める**(2026-10-04): git は自分の
                   -C と、それより前の確実な cd だけ。gh は -R/--repo・GH_REPO・PR の URL。
                   決められない(cd -・変数・条件付き cd 等)ときは例外を与えない。
  2. rm-guard    : 再帰 rm (-r/-rf) の破壊事故防止。
                   - 壊滅的ターゲット(/, ~, $HOME, システムdir, 裸の* 等) → 無条件 deny
                   - 相対パス / /tmp / $TMPDIR / ~/.worktrees 配下 → allow
                   - それ以外(絶対パス・解決できない変数展開) → deny
                   - `trash`(macOS のゴミ箱移動) は壊滅的ターゲット以外 allow。取り消せるので、
                     ユーザーが承認した片付けを Claude が完了できる(2026-10-03 承認)。
                     未マージ worktree は worktree-guard が止める
                   **通過マーカーは無い**(2026-09-23 廃止)。目的は「人に確認させる」
                   ことなので、Claude が自己申告で通せるなら確認が起きない。
                   同一コマンド内の単純な変数代入(`T=/tmp/x; rm -rf $T`)は解決してから
                   判定する(解決できたぶんだけ誤爆が減る)。
                   sudo/env/command/nohup/xargs 等のラッパー・`sh -c`・eval・( )・$( )・
                   `find -delete`/`-exec rm` も中を展開して同じ判定にかける(2026-10-04)。
  3. push-freshness : git push 前に origin/main より behind でないことを検証。
                   spinoff 等で古い main から切ったブランチを最新に追従させ、
                   テキスト競合だけでなく意味的ドリフト(シグネチャ変更等)を
                   merge+test で拾わせる。fetch できない(offline)/main 上/behind=0
                   なら素通り。behind>0 のみ deny。
                   **通過マーカーは無い**(2026-09-22 廃止)。hook 自身が behind を
                   再計算するので、「取り込んだ」という申告を信じる必要がない。
                   マーカー方式は Claude が文字列を足すだけで検証ゼロで通過できた。
"""
import json
import os
import re
import shlex
import subprocess
import sys

# 実行中の Bash コールの cwd (main で hook 入力から設定)。git 系ルールが参照する。
_CWD = None

HOME = os.path.normpath(os.path.expanduser("~"))   # $HOME の末尾 / や // で接頭辞判定が外れないように

SYSTEM_DIRS = {
    "/etc", "/usr", "/var", "/bin", "/sbin", "/opt",
    "/Library", "/System", "/Applications", "/Users", "/private",
}
SAFE_PREFIXES = (
    "/tmp/", "/private/tmp/",
    HOME + "/.worktrees/",
)
SAFE_VAR_PREFIXES = ("$TMPDIR", "${TMPDIR")


def deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def ask(reason: str) -> dict:
    """ユーザーに許可の確認を出させる。deny と違い、ユーザーがその場で通せる。"""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


# ---------------------------------------------------------------- merge-gate
# fallback 用（shlex で解析不能なセグメントのみ。解析可能なら下のトークン判定を使う）。
# **行頭にアンカーする**ことで、文字列リテラルの中に現れるだけのものを拾わない。
FALLBACK_CMD_RE = re.compile(
    r"^(?:\S*/)?"
    r"(?:gh\s+(?:pr|stack)\s+merge\b"
    r"|git\s+merge(?!-)(?!\s+--(?:abort|continue|quit|ff-only)))"
)
MERGE_RE = re.compile(
    r"\b(gh\s+pr\s+merge\b|gh\s+stack\s+merge\b|git\s+merge(?!-)(?!\s+--(abort|continue|quit|ff-only)))"
)


def _gh_positional(tokens: list) -> list:
    """gh の位置引数（-R/--repo の値は除く。`gh pr -R x merge` の形でも pr/merge を拾うため）。"""
    out, i = [], 1
    while i < len(tokens):
        a = tokens[i]
        if a in ("-R", "--repo"):
            i += 2
            continue
        if not a.startswith("-"):
            out.append(a)
        i += 1
    return out


def _is_merge_command(tokens: list, cwd=None, assigns=None) -> bool:
    """トークン列が実際の `gh pr merge` / `git merge` コマンドかを判定する。

    引用文字列の中に 'git merge' が現れるだけのコマンド（例: tmux send-keys で
    指示文を送る・echo で手順を出力する）を誤検知しないため、コマンド位置
    （先頭トークン。ラッパーは _unwrap が剥がす）だけを見る（2026-07-13 誤爆3件の恒久修正）。
    """
    if not tokens:
        return False
    base = os.path.basename(tokens[0])
    if base == "gh":
        rest = _gh_positional(tokens)
        # `gh stack merge` は stack 全段を一括マージする（stacked PRs・2026-07 public preview）。
        # `gh pr merge` は stacked PR に使えないため、stack 経路もここで受けないとゲートが素通りになる。
        return len(rest) >= 2 and rest[0] in ("pr", "stack") and rest[1] == "merge"
    if base == "git":
        _, sub, subargs = _git_parse(tokens, cwd, assigns or {})
        if sub == "merge":
            # --abort/--continue/--quit は merge 操作でない。--ff-only はポインタ移動のみで
            # 合成（Frankenstein マージ）が起こり得ないため対象外（例: local main の origin 同期）。
            return not any(s in ("--abort", "--continue", "--quit", "--ff-only") for s in subargs)
    return False


def _fallback_is_merge(seg: str) -> bool:
    """shlex が解析できないセグメント用の fallback。**コマンド位置でしか判定しない。**

    以前は seg 全体に MERGE_RE をかけていた。`_split_segments` は改行でも分割するので、
    python の heredoc やスクリプト本文が1行ずつセグメントになり、行内で引用符が閉じない
    行は shlex が ValueError を出して必ずこの fallback に落ちる。その結果、**文字列
    リテラルの中にマージコマンドが含まれているだけ**のスクリプト（この hook 自身を
    編集する python 等）で発火していた（2026-09-23 に実地で2回）。

    docstring にあった「誤分割しても評価が厳しくなる方向にしか倒れないので安全側」は、
    **安全側に倒れすぎて正当な作業が通らなくなる**ほうの実害を見落としていた。しかも
    そこから抜ける唯一の手段が自己申告マーカーなので、誤爆率の高さがマーカーを
    手放せない理由になっていた。
    """
    s = seg.strip()
    while True:  # 先頭の環境変数代入を読み飛ばす
        m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", s)
        if not m:
            break
        s = s[m.end():]
    return bool(FALLBACK_CMD_RE.match(s))


# 「マージは常にユーザー判断」の例外（Claude にマージを任せてよいリポ。OWNER/REPO 形式）。
# guards の設定 merge_allowed_repos（環境変数 CLAUDE_PLUGIN_OPTION_MERGE_ALLOWED_REPOS・
# カンマ区切り）から読む。未設定・空なら例外なし。ここを増やすのはユーザーの決定事項。
MERGE_ALLOWED_REPOS = frozenset(
    r.strip()
    for r in os.environ.get("CLAUDE_PLUGIN_OPTION_MERGE_ALLOWED_REPOS", "").split(",")
    if r.strip()
)


# `git merge` のソース ref を取り出すときに読み飛ばす、値を取るオプション
_MERGE_OPTS_WITH_VALUE = frozenset({
    "-m", "--message", "-S", "--gpg-sign", "-s", "--strategy",
    "-X", "--strategy-option", "-F", "--file",
})


def _merge_sources(subargs: list) -> list:
    """`git merge` の引数（サブコマンドより後ろ）からソース ref を返す。"""
    out, j = [], 0
    while j < len(subargs):
        a = subargs[j]
        if a in _MERGE_OPTS_WITH_VALUE:
            j += 2
            continue
        if not a.startswith("-"):
            out.append(a)
        j += 1
    return out


def _default_branch(cwd):
    """origin のデフォルトブランチ名。取れなければ None。"""
    r = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().split("/", 1)[-1]
    for cand in ("main", "master"):
        if _git(["rev-parse", "--verify", "--quiet",
                 "refs/remotes/origin/" + cand], cwd).returncode == 0:
            return cand
    return None


def _is_upstream_catchup(sources: list, cwd) -> bool:
    """現在のブランチに origin/<default> か origin/<current> を取り込むだけか。

    どちらも既にレビュー済みのリモート状態を1本のブランチへ入れるだけで、2本の
    in-flight ブランチを合成しない。ソースが1つでも安全集合の外にあれば False。
    """
    if not sources or cwd is None:
        return False
    r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if r.returncode != 0:
        return False
    cur = r.stdout.strip()
    safe = set()
    if cur and cur != "HEAD":
        safe.add("origin/" + cur)
    d = _default_branch(cwd)
    if d:
        safe.add("origin/" + d)
    return bool(safe) and all(s in safe for s in sources)


def _repo_slug(cwd, sole_origin=False):
    """origin の owner/repo。取れなければ None（＝例外に当たらない＝ask/deny 側）。

    sole_origin: gh はリモートが複数あると upstream 等を優先して操作対象を決めるので、
    origin 以外のリモートがあるときは origin の slug を操作対象とみなさない。"""
    if cwd is None:
        return None
    if sole_origin:
        r = _git(["remote"], cwd)
        if r.returncode != 0 or r.stdout.split() != ["origin"]:
            return None
    r = _git(["remote", "get-url", "origin"], cwd)
    if r.returncode != 0:
        return None
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", r.stdout.strip())
    return m.group(1) if m else None


def _norm_slug(v: str):
    """-R/--repo・GH_REPO の値（OWNER/REPO・HOST/OWNER/REPO・URL）を owner/repo にする。"""
    v = re.sub(r"^[a-z]+://", "", v.strip()).rstrip("/")
    v = re.sub(r"\.git$", "", v)
    parts = [p for p in v.split("/") if p]
    if len(parts) < 2 or "$" in v or "`" in v:
        return None
    return "/".join(parts[-2:])


_PR_COUNT_CACHE = {}


def _open_pr_count(cwd=None, slug=None):
    """オープン PR の件数。判定できなければ None（＝安全側）。

    slug があれば `gh pr list -R slug`（-R/--repo を付けたマージはそのリポに作用する）、
    無ければ cwd のリポで数える。"""
    key = (cwd, slug)
    if key in _PR_COUNT_CACHE:
        return _PR_COUNT_CACHE[key]
    n = None
    if slug:
        argv = ["gh", "pr", "list", "-R", slug, "--state", "open", "--json", "number"]
        run_cwd = _CWD if (_CWD and os.path.isdir(_CWD)) else None
    elif cwd is not None:
        argv = ["gh", "pr", "list", "--state", "open", "--json", "number"]
        run_cwd = cwd
        r = _git(["remote"], cwd)
        if r.returncode != 0:
            argv = None            # git リポでない等
        elif not r.stdout.strip():
            argv, n = None, 0      # remote が無いリポに PR は存在しえない
    else:
        argv = None
    if argv:
        try:
            proc = subprocess.run(argv, cwd=run_cwd, capture_output=True, text=True, timeout=10)
            if proc.returncode == 0:
                n = len(json.loads(proc.stdout or "[]"))
        except (subprocess.TimeoutExpired, ValueError, OSError):
            n = None               # 未認証・オフライン等
    _PR_COUNT_CACHE[key] = n
    return n


def _merge_target(cmd):
    """マージコマンド1つが作用するリポ。returns dict(kind, cwd, slug, sources) か None(判定不能)。

    **リポはそのコマンド自身のトークンから決める。** 以前はコマンド全体の最初の
    `git -C <path>` や cd を見ていたので、別セグメントのおとり（`git -C <remote 無し> status;
    gh pr merge -R <他リポ>`）で判定対象のリポをすり替えられた。"""
    if cmd.opaque:
        return None
    toks = cmd.tokens
    if os.path.basename(toks[0]) == "git":
        if any(k in cmd.env for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")):
            return None
        gcwd, _, subargs = _git_parse(toks, cmd.cwd, cmd.assigns)
        if gcwd is None or not os.path.isdir(gcwd):
            return None
        return {"kind": "git", "cwd": gcwd, "slug": _repo_slug(gcwd),
                "sources": _merge_sources(subargs)}
    # gh: 操作対象のリポは -R/--repo・GH_REPO・PR の URL のどれかで上書きされうる
    slugs = set()
    if "GH_REPO" in cmd.env:
        slugs.add(_norm_slug(_resolve(cmd.env["GH_REPO"], cmd.assigns)))
    i = 1
    while i < len(toks):
        a = toks[i]
        if a in ("-R", "--repo"):
            slugs.add(_norm_slug(_resolve(toks[i + 1], cmd.assigns)) if i + 1 < len(toks) else None)
            i += 2
            continue
        if a.startswith("--repo="):
            slugs.add(_norm_slug(_resolve(a.split("=", 1)[1], cmd.assigns)))
        elif a.startswith("-R") and len(a) > 2:
            slugs.add(_norm_slug(_resolve(a[2:], cmd.assigns)))
        else:
            m = re.match(r"^https?://[^/]+/([^/]+/[^/]+)/pull/\d+", a)
            if m:
                slugs.add(m.group(1))
        i += 1
    if slugs:
        if None in slugs or len(slugs) != 1 or _gh_positional(toks)[0] != "pr":
            return None            # 解決できない・食い違う・gh stack での上書き
        return {"kind": "gh", "cwd": None, "slug": slugs.pop(), "sources": []}
    if cmd.cwd is None:
        return None
    return {"kind": "gh", "cwd": cmd.cwd, "slug": _repo_slug(cmd.cwd, sole_origin=True),
            "sources": []}


def _merge_exempt(t) -> bool:
    """このマージがゲートの例外に当たるか。リポを特定できないものは例外にしない。"""
    if t is None:
        return False
    # このゲートが守るのは「複数のオープン PR/ブランチが絡むマージ」。オープン PR が
    # 0 件なら守る対象が無い（使い捨ての検証リポ・remote 無しのローカルリポ等）。
    # cwd が無いのは -R 等でリポを明示した gh だけ（そのリポで数える）。
    if (_open_pr_count(cwd=t["cwd"]) if t["cwd"] else _open_pr_count(slug=t["slug"])) == 0:
        return True
    # guards の設定 merge_allowed_repos のリポだけは Claude 判断でマージしてよい。
    if t["slug"] and t["slug"] in MERGE_ALLOWED_REPOS:
        return True
    # upstream 追いつきマージ（origin/<default> か origin/<current> を現在のブランチへ）は
    # 2本の in-flight ブランチを合成しないので対象外。push-freshness が手順(1)として
    # 指示しているのがこれで、塞ぐと両ルールが矛盾する(2026-09-23)。
    return t["kind"] == "git" and _is_upstream_catchup(t["sources"], t["cwd"])


def rule_merge_gate(command: str):
    # **通過マーカーは持たない**(2026-09-23 廃止)。以前は特定の環境変数を先頭に
    # 付ければ検証の中身を見ずに素通りしたが、それは Claude が自分で立てられる
    # 「自己申告」だった。CLAUDE.md が「マージは常にユーザー判断」と定めている以上、
    # 証跡を積んで Claude に通させる設計自体が方針と食い違う。判断する人に返す。
    targets = []
    for cmd in _commands(command):
        if cmd.opaque:
            if _fallback_is_merge(cmd.raw) or _is_merge_command(cmd.tokens):
                targets.append(None)   # 解析できずリポもソースも特定できない
            continue
        if _is_merge_command(cmd.tokens, cmd.cwd, cmd.assigns):
            targets.append(_merge_target(cmd))
    if not targets:
        return None
    # マージコマンドが複数あれば、すべてが例外に当たるときだけ通す。
    if all(_merge_exempt(t) for t in targets):
        return None
    checklist = (
        "複数のオープンPR/ブランチが絡むマージでは、実行前に次を検証すること:\n"
        "(1) `gh pr list --state open` で全オープンPRと mergeable を確認\n"
        "(2) 各PRの変更ファイルを `gh pr view <N> --json files` で取得し `comm -12` で重複特定\n"
        "(3) 重複ファイルは `gh pr diff <N>` でハンク位置の競合を突合\n"
        "(4) `git merge-tree --write-tree <br1> <br2>` で実マージ合成を検証(CONFLICTマーカー無し確認)\n"
        "(5) 合成ツリーから `git cat-file -p <tree>:<path>` で実ファイルを取得し新旧シンボル両立を確認\n"
        "※ `gh stack merge` は stack 全段が一括で入る。stack 内の層同士は依存関係として"
        "設計済みなので、検証対象は **stack 外の open PR との重複**。\n"
    )
    # 確認なしで動くセッション（spinoff 等の bypassPermissions）では ask が誰にも見られずに
    # 通るおそれがあるので、従来どおり止める。人が見ているセッションでは ask にして、
    # マージの判断をその場のユーザーに返す（2026-09-24 承認: 取引先リポの改修セッションで
    # 毎回ユーザーが別経路で打ち直すのはテンポが悪いため）。
    if _PERMISSION_MODE == "bypassPermissions":
        return deny(
            "🛑 merge前デグレ検証ゲート(グローバルhook):\n"
            + checklist
            + "**確認なしのモード（bypassPermissions）では、このマージは実行できない。**\n"
            "CLAUDE.md がマージを常にユーザー判断と定めているため(例外は guards の設定 merge_allowed_repos に書いたリポのみ)。"
            "上の検証を済ませたうえで、何をどのブランチへ入れるのか・重複の有無・検証結果をユーザーに説明し、"
            "ユーザーにマージしてもらうこと。"
        )
    return ask(
        "🛑 merge前デグレ検証ゲート(グローバルhook):\n"
        + checklist
        + "**マージはユーザー判断**(例外は guards の設定 merge_allowed_repos に書いたリポのみ)。"
        "Claude はこの確認を出す前に上の検証を済ませ、何をどのブランチへ入れるのか・重複の有無・"
        "検証結果をユーザーに説明していること。ユーザーはその説明を見てから許可する。"
    )


# ------------------------------------------------------------------ rm-guard
HEREDOC_RE = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _strip_heredocs(command: str) -> str:
    """heredoc の本文を落とす。本文はコマンドではなくデータ（issue 本文・SQL 等）。"""
    out, pending = [], []
    for line in command.split("\n"):
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
            continue
        out.append(line)
        pending.extend(m.group(2) for m in HEREDOC_RE.finditer(line))
    return "\n".join(out)


SUBST = "$__SUBST__"   # コマンド置換を外側のセグメントに残すときの印（解決不能な変数として扱われる）


def _parse_segments(command: str) -> list:
    """コマンドを単純コマンド単位のセグメントに分ける。

    返り値は dict(text, depth, before, after) のリスト。before/after は前後の区切り
    （'^' 先頭, '$' 末尾, ';' '&&' '||' '|' '&' '\\n' '(' ')'）。
    - 引用符の中では分割しない（中はデータ）。ただし `$( )` とバッククォートは
      ダブルクォートの中でも実行されるので、中身を別セグメント(depth+1)として取り出す
    - 引用符の外の `( )` もサブシェルとして中身を別セグメント(depth+1)にする
    - `2>&1` `&>` の & は区切りではない
    """
    s = _strip_heredocs(command)
    out = []
    st = {"buf": [], "before": "^", "depth": 0, "quote": None}
    stack = []   # (closer, 外側の状態)

    def flush(sep):
        out.append({"text": "".join(st["buf"]), "depth": st["depth"],
                    "before": st["before"], "after": sep})
        st["buf"] = []
        st["before"] = sep

    def open_subst(closer):
        stack.append((closer, dict(st, buf=list(st["buf"]))))
        st.update(buf=[], before="(", depth=st["depth"] + 1, quote=None)

    def close_subst():
        flush(")")
        closer, outer = stack.pop()
        st.update(outer)
        if closer != "(":           # $( ) / ` ` は外側の語の一部として印を残す
            st["buf"].append(SUBST)
        else:
            st["before"] = ")"

    i = 0
    while i < len(s):
        c = s[i]
        q = st["quote"]
        top = stack[-1][0] if stack else None
        if q == "'":
            st["buf"].append(c)
            if c == "'":
                st["quote"] = None
            i += 1
            continue
        if c == "\\" and i + 1 < len(s):
            st["buf"].append(s[i:i + 2]); i += 2
            continue
        if top == "`" and c == "`":
            close_subst(); i += 1
            continue
        if s.startswith("$(", i):
            open_subst(")"); i += 2
            continue
        if c == "`":
            open_subst("`"); i += 1
            continue
        if q == '"':
            st["buf"].append(c)
            if c == '"':
                st["quote"] = None
            i += 1
            continue
        if c in "'\"":
            st["quote"] = c; st["buf"].append(c); i += 1
            continue
        if c == ")":
            if top in (")", "("):
                close_subst()
            else:
                flush(")")          # case のパターン等。区切りとして扱う
            i += 1
            continue
        if c == "(":
            flush("(")
            stack.append(("(", dict(st, buf=[])))
            st.update(buf=[], before="(", depth=st["depth"] + 1)
            i += 1
            continue
        two = s[i:i + 2]
        if two in ("&&", "||", "|&", ";;"):
            flush(two); i += 2
            continue
        if c == "&" and (s[i + 1:i + 2] == ">" or (i > 0 and s[i - 1] in "<>")):
            st["buf"].append(c); i += 1   # リダイレクト（2>&1 / &>）
            continue
        if c in "|;&\n":
            flush(c); i += 1
            continue
        st["buf"].append(c)
        i += 1
    flush("$")
    while stack:                      # 閉じていない括弧: 外側の残りも捨てずに評価する
        _, outer = stack.pop()
        st.update(outer)
        flush("$")
    return out


def _split_segments(command: str):
    """パイプ/セミコロン/&&/改行/サブシェル/コマンド置換で分割したテキストのリスト。"""
    return [seg["text"] for seg in _parse_segments(command)]


VAR_REF_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
ASSIGN_TOKEN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)


def _resolve(raw: str, assigns: dict) -> str:
    """判明している代入だけを展開する。未知の変数はそのまま残す（＝other に倒れる）。"""
    if not assigns:
        return raw

    def sub(m):
        v = assigns.get(m.group(1))
        return v if v is not None else m.group(0)
    return VAR_REF_RE.sub(sub, raw)


def _resolved_value(raw: str, assigns: dict):
    """代入の右辺を静的に解決する。解決できなければ None（＝その変数は以後 unknown）。"""
    v = _resolve(raw, assigns)
    if "$" in v or "`" in v:
        return None
    return os.path.expanduser(v) if v.startswith("~") else v


# ------------------------------------------------- 単純コマンドの列挙（全ルール共通）
# 実行を別コマンドへ渡すだけのラッパー。読み飛ばして中のコマンドを評価する。
# 値を取るオプションは次のトークンも読み飛ばす。
_WRAPPER_OPTS_WITH_VALUE = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-r", "-t", "-T", "-U"},
    "doas": {"-u", "-C"},
    "nice": {"-n", "--adjustment"},
    "exec": {"-a"},
    "time": set(),
    "nohup": set(),
    "command": set(),
    "builtin": set(),
    "caffeinate": {"-t", "-w"},
    "stdbuf": {"-i", "-o", "-e"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "gtimeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-n", "-P", "-L", "-s", "-E", "-d", "-a", "--max-args", "--max-procs",
              "--max-lines", "--max-chars", "--eof", "--delimiter", "--arg-file", "--replace"},
}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until", "fi", "done", "coproc"}


def _unwrap(tokens: list):
    """ラッパーを剥がす。returns (env, tokens, nested, flags)

    env    : 先頭（とラッパー中）の環境変数代入
    tokens : 実際に実行されるコマンド（空なら代入だけ or 中身は nested）
    nested : `sh -c STR` / `eval ...` / `env -S STR` の文字列（再帰して評価する）
    flags  : {'xargs': 引数が標準入力から来る, 'shell_state': eval/source のように
              今のシェルの cwd・変数を書き換えうる, 'chdir': env -C で cwd が変わる}
    """
    env, nested, flags = {}, [], {"xargs": False, "shell_state": False, "chdir": False}
    t = list(tokens)
    while t:
        while t and t[-1] == "}":
            t.pop()
        if not t:
            break
        h = t[0]
        m = ASSIGN_TOKEN_RE.match(h)
        if m:
            env[m.group(1)] = m.group(2)
            t.pop(0)
            continue
        if h in _KEYWORDS:
            t.pop(0)
            continue
        b = os.path.basename(h)
        if b in ("command", "builtin") and len(t) > 1 and t[1] in ("-v", "-V"):
            break   # 実行ではなく問い合わせ
        if b == "env":
            t.pop(0)
            while t:
                a = t[0]
                if ASSIGN_TOKEN_RE.match(a):
                    k, v = a.split("=", 1); env[k] = v; t.pop(0)
                elif a in ("-u", "--unset"):
                    del t[:2]
                elif a in ("-C", "--chdir") or a.startswith("--chdir="):
                    flags["chdir"] = True
                    del t[:1 if "=" in a else 2]
                elif a in ("-S", "--split-string") or a.startswith("--split-string="):
                    val = a.split("=", 1)[1] if "=" in a else (t[1] if len(t) > 1 else "")
                    rest = t[1:] if "=" in a else t[2:]
                    try:
                        t = shlex.split(val) + rest
                    except ValueError:
                        nested.append(val); t = []
                    break
                elif a.startswith("-"):
                    t.pop(0)
                else:
                    break
            continue
        if b in _WRAPPER_OPTS_WITH_VALUE:
            with_val = _WRAPPER_OPTS_WITH_VALUE[b]
            if b == "xargs":
                flags["xargs"] = True
            t.pop(0)
            while t and t[0].startswith("-") and t[0] != "-":
                a = t.pop(0)
                if a == "--":
                    break
                if a in with_val and t:
                    t.pop(0)
            if b in ("timeout", "gtimeout") and t:
                t.pop(0)   # DURATION
            while b == "sudo" and t and ASSIGN_TOKEN_RE.match(t[0]):
                k, v = t.pop(0).split("=", 1); env[k] = v
            continue
        if b in _SHELLS:
            for j in range(1, len(t)):
                a = t[j]
                if not a.startswith("-"):
                    break
                if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a):
                    if j + 1 < len(t):
                        nested.append(t[j + 1])
                    t = []
                    break
            break
        if b == "eval":
            nested.append(" ".join(t[1:]))
            flags["shell_state"] = True
            t = []
            break
        if b in ("source", "."):
            flags["shell_state"] = True
        break
    return env, t, nested, flags


def _certain(seg: dict) -> bool:
    """このセグメントが今のシェルで必ず実行されるか（cd・変数代入が後続に効くと言えるか）。

    サブシェルの中・条件付き（`a && cd x` / `a || cd x`）・パイプ・バックグラウンドの
    cd や代入は、後続に効くとは限らない。"""
    return (seg["depth"] == 0 and seg["before"] in ("^", ";", "\n", "&", ";;")
            and seg["after"] not in ("|", "|&", "&"))


def _resolve_cd(tokens: list, cur, assigns: dict):
    """`cd [-L|-P] [dir]` の移動先。判定不能なら None。"""
    args = [a for a in tokens[1:] if a not in ("-L", "-P", "-e", "-@")]
    if not args:
        return HOME
    if len(args) > 1 or args[0] == "-":
        return None
    v = _resolved_value(args[0], assigns)
    if v is None:
        return None
    if not os.path.isabs(v):
        # CDPATH があると相対名の行き先が変わる
        if cur is None or (os.environ.get("CDPATH") and not v.startswith(".")):
            return None
        v = os.path.join(cur, v)
    v = os.path.normpath(v)
    return v if os.path.isdir(v) else None


class Cmd:
    """列挙された単純コマンド1つ。cwd は実行される作業ディレクトリ（判定不能なら None）。"""
    __slots__ = ("env", "tokens", "cwd", "raw", "opaque", "xargs", "assigns")

    def __init__(self, env, tokens, cwd, raw, opaque, xargs, assigns):
        self.env, self.tokens, self.cwd, self.raw = env, tokens, cwd, raw
        self.opaque, self.xargs, self.assigns = opaque, xargs, assigns


_CMDS_CACHE = {}


def _commands(command: str) -> list:
    """command に含まれる単純コマンドを、ラッパー・`sh -c`・eval・サブシェル・コマンド置換の
    中まで展開して列挙する（全ルール共通。メモ化）。"""
    key = (command, _CWD)
    if key not in _CMDS_CACHE:
        start = _CWD if (_CWD and os.path.isdir(_CWD)) else None
        _CMDS_CACHE[key] = list(_walk(command, start, {}, 0))
    return _CMDS_CACHE[key]


def _walk(command: str, cwd, assigns: dict, level: int):
    if level > 4:
        yield Cmd({}, [], None, command, True, False, {})
        return
    cur, assigns = cwd, dict(assigns)
    funcs = False   # 関数が定義された（cd 等が上書きされうる）
    for seg in _parse_segments(command):
        text = seg["text"].strip()
        if not text:
            continue
        try:
            raw_tokens = shlex.split(text)
            opaque = False
        except ValueError:
            raw_tokens = text.split()
            opaque = True
        if (seg["after"] == "(" and len(raw_tokens) == 1) or raw_tokens[:1] == ["function"]:
            # 関数定義（`cd() { :; }` / `function cd {…}`）。以後 cd 等の意味が変わりうるので
            # 以後の cwd は判定不能にする（定義の本体は後続セグメントとして評価される）
            cur, funcs = None, True
            assigns = {k: None for k in assigns}
            continue
        env, tokens, nested, flags = _unwrap(raw_tokens)
        certain = _certain(seg)
        b = os.path.basename(tokens[0]) if tokens else ""
        here = None if flags["chdir"] else cur
        yield Cmd(env, tokens, here, text, opaque, flags["xargs"], dict(assigns))
        for n in nested:
            yield from _walk(n, here, assigns, level + 1)
        # ---- このセグメントが今のシェルの状態（変数・cwd）をどう変えるか
        if not tokens and env:                      # 純粋な代入 `T=/tmp/x`
            for k, v in env.items():
                assigns[k] = _resolved_value(v, assigns) if certain else None
        elif b in ("export", "declare", "typeset", "local", "readonly"):
            for a in tokens[1:]:
                m = ASSIGN_TOKEN_RE.match(a)
                if m:
                    assigns[m.group(1)] = _resolved_value(m.group(2), assigns) if certain else None
        elif b in ("read", "unset", "for", "select", "getopts", "mapfile", "readarray", "printf"):
            for a in tokens[1:]:
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", a):
                    assigns[a] = None
        if flags["shell_state"]:
            cur = None
            assigns = {k: None for k in assigns}
        elif b in ("cd", "pushd"):
            cur = _resolve_cd(tokens, cur, assigns) if (certain and b == "cd" and not funcs) else None
        elif b == "popd":
            cur = None


def _git_parse(tokens: list, cwd, assigns: dict):
    """`git [global opts] <sub> <args>` を読む。returns (gitcwd, sub, subargs)。

    -C は重ねると連結される（git -C a -C b == a/b）。--git-dir / --work-tree は
    どのリポに作用するか静的に決めきれないので gitcwd=None。"""
    args, i, gcwd = tokens[1:], 0, cwd
    while i < len(args):
        a = args[i]
        if a == "-C":
            v = _resolved_value(args[i + 1], assigns) if i + 1 < len(args) else None
            if v is None or gcwd is None and not os.path.isabs(v):
                gcwd = None
            elif v:
                gcwd = os.path.normpath(os.path.join(gcwd or "/", v))
            i += 2
            continue
        if a in ("--git-dir", "--work-tree"):
            gcwd = None; i += 2
            continue
        if a.startswith(("--git-dir=", "--work-tree=")):
            gcwd = None; i += 1
            continue
        if a in ("-c", "--namespace", "--exec-path", "--config-env", "--super-prefix"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        break
    sub = args[i] if i < len(args) else None
    return gcwd, sub, args[i + 1:]


def _classify_target(raw: str, assigns: dict = None) -> str:
    """returns: 'catastrophic' | 'safe' | 'other'"""
    t = raw.strip().strip('"').strip("'")
    if not t:
        return "safe"
    if t.startswith(SAFE_VAR_PREFIXES):
        return "safe"
    if "$" in t or "`" in t:
        t = _resolve(t, assigns or {})
    if "$" in t or "`" in t:
        return "other"  # 解決できなかった変数/コマンド置換は静的に判定不能
    expanded = os.path.expanduser(t) if t.startswith("~") else t
    norm = os.path.normpath(expanded)
    stripped_glob = norm[:-2] if norm.endswith("/*") else norm
    # 壊滅的: ルート・ホーム・システムdir・裸のグロブ・カレント全体
    if t in {"*", ".", "./", "..", "../", ".*"}:
        return "catastrophic"
    if stripped_glob in {"/", HOME} or stripped_glob in SYSTEM_DIRS:
        return "catastrophic"
    if norm == "/*":
        return "catastrophic"
    # 安全: 相対パス（.. を含まない）
    if not norm.startswith("/") and ".." not in norm.split(os.sep):
        return "safe"
    # 安全: 一時領域・worktree 配下
    if norm.startswith(SAFE_PREFIXES) or (norm + "/").startswith(SAFE_PREFIXES):
        return "safe"
    return "other"


_RECURSIVE_FLAG_RE = re.compile(r"^-[a-zA-Z]*[rR]")
_FIND_ACTIONS = ("-exec", "-execdir", "-ok", "-okdir")


def _is_recursive_rm(tokens: list) -> bool:
    return any(_RECURSIVE_FLAG_RE.match(f) or f == "--recursive"
               for f in tokens[1:] if f.startswith("-") and f != "--")


def _find_delete_starts(tokens: list):
    """`find <start>... -delete` / `-exec rm ...` なら開始パスのリスト、削除しない find なら None。

    find は開始パス配下を再帰的にたどるので、削除アクション付きなら開始パスの再帰削除とみなす。"""
    if not tokens or os.path.basename(tokens[0]) != "find":
        return None
    deleting = "-delete" in tokens
    for i, a in enumerate(tokens):
        if a in _FIND_ACTIONS:
            action = []
            for b in tokens[i + 1:]:
                if b in (";", "+"):
                    break
                action.append(b)
            if re.search(r"(^|[\s/;&|(`])(rm|unlink|trash)(\s|$)", " ".join(action)):
                deleting = True
    if not deleting:
        return None
    starts, i = [], 1
    while i < len(tokens) and tokens[i] in ("-H", "-L", "-P", "-E", "-X", "-d", "-s", "-x"):
        i += 1
    while i < len(tokens) and not tokens[i].startswith(("-", "(", "!", ")")):
        starts.append(tokens[i]); i += 1
    return starts


_OPAQUE_DELETE_RE = re.compile(r"(^|[\s;&|(`/])(rm|find|trash)\s")
_OPAQUE_ABS_RE = re.compile(r"(^|\s)[\"']?(/|~|\$\{?HOME)")


def rule_rm_guard(command: str):
    # **通過マーカーは持たない**(2026-09-23 廃止)。以前は特定の環境変数を先頭に
    # 付ければ素通りしたが、それは Claude 自身が立てられる「自己申告」だった。
    # このルールの目的は**人に確認させること**なので、Claude が自分で通せるなら確認は起きない。
    # push-freshness と違い rm には「安全である」ことを測る方法が無く、判断そのものが要る。
    # だから判断する人に返す＝Claude には通させない。
    # sudo/env/xargs 等のラッパー・`sh -c`・eval・サブシェル・コマンド置換の中も _commands が展開する。
    worst = None  # None < other < catastrophic

    def note(c):
        nonlocal worst
        if c == "catastrophic":
            worst = "catastrophic"
        elif c == "other" and worst is None:
            worst = "other"

    for cmd in _commands(command):
        tokens, assigns = cmd.tokens, cmd.assigns
        if cmd.opaque and _OPAQUE_DELETE_RE.search(cmd.raw) and _OPAQUE_ABS_RE.search(cmd.raw):
            note("other")   # 引用符が閉じていない等で正しく読めない削除は安全側
        if not tokens:
            continue
        cmd_name = os.path.basename(tokens[0])
        targets = [t for t in tokens[1:] if not t.startswith("-")]
        if cmd.xargs:
            targets.append("$__XARGS__")   # 引数は標準入力から来る＝静的に判定不能
        if cmd_name == "trash":
            # ゴミ箱へ移すだけで取り消せるので、安全領域外でも通す。壊滅的ターゲットだけ止める
            if any(_classify_target(t, assigns) == "catastrophic" for t in targets):
                note("catastrophic")
            continue
        starts = _find_delete_starts(tokens)
        if starts is not None:
            for t in starts:
                # `find . -name x -delete` のように条件で絞るのが普通なので、カレントの . は相対扱い
                note("safe" if t in (".", "./") else _classify_target(t, assigns))
            continue
        if cmd_name != "rm" or not _is_recursive_rm(tokens):
            continue
        for t in targets:
            note(_classify_target(t, assigns))
    if worst == "catastrophic":
        return deny(
            "🛑 rm-guard(グローバルhook): 壊滅的な再帰削除ターゲット(ルート/ホーム/システムdir/裸の * 等)を検出。"
            "この操作は許可できない。本当に必要ならユーザーに明示承認を取り、対象を具体的なパスに絞って出し直すこと。"
        )
    if worst == "other":
        return deny(
            "⚠️ rm-guard(グローバルhook): 一時領域・相対パス以外への再帰削除を検出。\n"
            "**このゲートを黙らせる環境変数やマーカーは無い。rm -r では消せない。**\n"
            "次のどれかにすること:\n"
            "  (1) 対象が /tmp・$TMPDIR・~/.worktrees 配下、または相対パスで済むなら書き直す\n"
            "  (2) 変数で書いているなら、同じコマンドの中で代入するか、リテラルのパスに展開する\n"
            "  (3) macOS なら `trash <パス>` でゴミ箱へ移す（取り消せるので通る。ユーザーが削除を承認済みのときに限る）\n"
            "  (4) trash が無い環境（Linux 等）なら、**何をなぜ消すのかをユーザーに説明し、ユーザーに実行してもらう**\n"
            "(確認すべきこと: 削除対象は目的の特定パスか / 未コミットの作業・"
            "他セッションの worktree を巻き込まないか)"
            "(ユーザー資産に触る場合は先にユーザー承認を取ること)。"
            "sudo・xargs・sh -c・eval・find -delete 等で包んでも同じ判定になる。"
        )
    return None


# ------------------------------------------------------------ push-freshness
PUSH_RE = re.compile(r"\bgit\s+push\b")


def _effective_cwd(command: str):
    """git 系ルールが見るべき作業ディレクトリ。ツールの cwd ではなく、コマンド内の
    `cd <path> && …` や `git -C <path> …` を追って、実際に git が走るディレクトリを返す。
    （実害: `cd ~/.claude/skills && git commit` を別リポの cwd で判定して誤 deny・2026-09-21）
    判定不能ならツールの cwd。"""
    cwd = _CWD if (_CWD and os.path.isdir(_CWD)) else None
    if not command:
        return cwd
    m = re.search(r"\bgit\s+-C\s+(\S+)", command)
    if m:
        cand = os.path.expanduser(m.group(1).strip("'\""))
        cand = cand if os.path.isabs(cand) else os.path.join(cwd or os.getcwd(), cand)
        return cand if os.path.isdir(cand) else cwd
    cur = cwd
    for seg in re.split(r"&&|;|\|\||\n", command):
        m = re.match(r"\s*cd\s+(\S+)", seg)
        if m:
            cand = os.path.expanduser(m.group(1).strip("'\""))
            cand = cand if os.path.isabs(cand) else os.path.join(cur or os.getcwd(), cand)
            if os.path.isdir(cand):
                cur = os.path.normpath(cand)
        if re.search(r"\bgit\s+(commit|push)\b", seg):
            return cur
    return cur

def _git(args, cwd, timeout=8):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )


def rule_push_freshness(command: str):
    # **通過マーカーは持たない。** 以前は特定の環境変数を command の先頭に付ければ
    # 検証の中身を一切見ずに素通りさせていたが、それは Claude 自身が文字列を足すだけで
    # 立てられる「自己申告」だった（検証を1つも実施せずにゲートを通過できた）。
    # このルールが求めているのは「最新を取り込んだ」という申告ではなく、その**結果**であり、
    # 結果は下で behind 数として機械的に測れる。測れるものを申告で代替しない。
    if not PUSH_RE.search(command):
        return None
    cwd = _effective_cwd(command)
    if cwd is None:
        return None
    try:
        # git repo か / 現ブランチ
        r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        if r.returncode != 0:
            return None
        branch = r.stdout.strip()
        if branch in ("main", "master", "HEAD"):
            return None  # main 系を push するときは対象外
        # origin/main を取得 (network。offline/slow は素通りさせる=push は元々 network 前提)
        _git(["fetch", "origin", "main", "--quiet"], cwd)
        r = _git(["rev-list", "--count", "HEAD..origin/main"], cwd)
        if r.returncode != 0:
            return None
        behind = int(r.stdout.strip() or "0")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None  # 判定不能なら邪魔しない
    if behind == 0:
        return None
    return deny(
        f"🛑 push-freshness ゲート(グローバルhook): 現ブランチ '{branch}' は "
        f"origin/main より {behind} commits 遅れています。\n"
        "古い main から切ったまま push すると、テキスト競合だけでなく "
        "意味的ドリフト(関数シグネチャ変更等・自動マージは通るが実行時に壊れる)を "
        "見落とします。push 前に最新を取り込み、テストで両立を確認すること:\n"
        "  (1) git merge origin/main   (競合は解消)\n"
        "  (2) プロジェクトのテスト/ビルドをフル実行し pass を確認\n"
        "  (3) そのまま push を再実行する\n"
        "(rebase 運用なら merge の代わりに git rebase origin/main でも可)。\n"
        "**このゲートを黙らせる環境変数やマーカーは無い。** behind が 0 になれば自動的に通る。\n"
        "古い base を意図して push する必要がある場合(backport 等)は、Claude ではなく"
        "ユーザーが直接実行すること。"
    )


# ----------------------------------------------------- main-commit-freshness
COMMIT_RE = re.compile(r"\bgit\s+commit\b")


def rule_main_commit_freshness(command: str):
    """古い main の上に commit を積むのを止める。

    rule_push_freshness は feature ブランチ専用（main は明示的に対象外）なので、
    「ローカル main 自体が古い」は誰も見ていなかった。マージは remote で起きるため
    ローカル main は自動追従せず、pull を忘れると古い main の上に積む → push は
    non-fast-forward で弾かれ、rebase のやり直しになる。

    ここは PostToolUse の additionalContext ではなく deny が正しい: commit させてから
    「古かったよ」と言うより、積む前に止める方が手戻りが無い。merge 後の pull 追従は
    止める対象が無いので git-freshness.py(PostToolUse) が担当する。
    """
    if not COMMIT_RE.search(command):
        return None
    commits = [c for c in _commands(command) if c.tokens
               and os.path.basename(c.tokens[0]) == "git"
               and _git_parse(c.tokens, c.cwd, c.assigns)[1] == "commit"]
    # マーカーは commit コマンド自身の先頭の環境変数代入としてだけ効く（echo や
    # コメントに書いた文字列では通らない）。
    if commits and all(_marker(c, "MAIN_FRESHNESS_OK") for c in commits):
        return None
    cwd = _effective_cwd(command)
    if cwd is None:
        return None
    try:
        r = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
        if r.returncode != 0:
            return None
        branch = r.stdout.strip()
        if branch not in ("main", "master"):
            return None  # feature ブランチは rule_push_freshness が push 時に見る
        # fetch は best-effort（offline なら素通り＝commit を邪魔しない）
        _git(["fetch", "origin", branch, "--quiet"], cwd)
        r = _git(["rev-list", "--count", f"HEAD..origin/{branch}"], cwd)
        if r.returncode != 0:
            return None
        behind = int(r.stdout.strip() or "0")
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None  # 判定不能なら邪魔しない
    if behind == 0:
        return None
    return deny(
        f"🛑 main-freshness ゲート(グローバルhook): ローカル '{branch}' は "
        f"origin/{branch} より {behind} commits 遅れています。\n"
        "このまま commit すると push が non-fast-forward で弾かれ、積み直しになります。"
        "さらに scheduler の shell ジョブは main チェックアウトを直に実行するため、"
        "古い main のままだと**マージ済みのコードが live にならない**穴もあります。\n"
        "  (1) git pull --ff-only origin main   (未コミット変更があり衝突するなら先に commit/stash。"
        "自動 stash は事故るので手動で判断すること)\n"
        "  (2) 問題なければ commit を再実行\n"
        "意図的に古い main の上に積む場合のみ、先頭に `MAIN_FRESHNESS_OK=1 ` を付けて再実行。"
    )


# ------------------------------------------------------------- worktree-guard
# 未マージ worktree の削除禁止（グローバル CLAUDE.md「⚠️ 未マージ worktree は絶対に削除しない」の強制点。
# rm-guard は ~/.worktrees/ を SAFE 扱いするため、このルールが rm-guard より先に立つ必要がある）
WORKTREES_PREFIX = HOME + "/.worktrees/"


def _worktree_state(path: str):
    """'merged_clean' | 'unmerged' | 'unknown'"""
    p = os.path.normpath(os.path.expanduser(path))
    if not os.path.isdir(p):
        return "unknown"
    try:
        if _git(["status", "--porcelain"], p).stdout.strip():
            return "unmerged"  # dirty＝未回収の作業がある
        # どれか1つの base に HEAD が完全包含されていればマージ済み。
        # 最初に解決できた base だけで判定しない — origin/main がローカル main より
        # 古い repo では「ローカル main へ取り込み済み」を見逃して deny する（実測21コミット差）。
        resolved = False
        for base in ("origin/main", "main", "origin/master", "master"):
            r = _git(["rev-list", "--count", "HEAD", "^" + base], p)
            if r.returncode == 0:
                resolved = True
                if int(r.stdout.strip() or "0") == 0:
                    return "merged_clean"
        # squash merge は main に別 SHA の1コミットを作るので、トポロジーでは永久に未マージに見える。
        # このブランチの MERGED PR の head が現 HEAD と一致すれば、作業は main に入っている
        # （spinoff-session の reap.sh と同じ判定。gh が無い・失敗・不一致は従来どおり）
        if _squash_merged(p):
            return "merged_clean"
        return "unmerged" if resolved else "unknown"
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return "unknown"


def _squash_merged(p: str) -> bool:
    branch = _git(["symbolic-ref", "--short", "-q", "HEAD"], p).stdout.strip()
    head = _git(["rev-parse", "HEAD"], p).stdout.strip()
    if not branch or not head:
        return False
    try:
        r = subprocess.run(
            ["gh", "pr", "list", "--head", branch, "--state", "merged",
             "--json", "headRefOid", "--jq", ".[].headRefOid"],
            cwd=p, capture_output=True, text=True, timeout=8,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0 and head in r.stdout.split()


def _marker(cmd, name: str) -> bool:
    """通過マーカー（`NAME=1 <cmd>`）がそのコマンド自身の先頭の環境変数代入として付いているか。
    以前はコマンド文字列のどこかに含まれれば通していたので、echo やコメントでも通った。"""
    return cmd.env.get(name) == "1"


def _under_worktrees(p: str) -> bool:
    return p == WORKTREES_PREFIX.rstrip("/") or p.startswith(WORKTREES_PREFIX)


def _inside_worktree(p: str) -> bool:
    """p が worktree の中のサブパス（worktree の root そのものでも、root を含む上位でもない）か。"""
    d = p
    while d and not os.path.isdir(d):
        d = os.path.dirname(d)
    if not d:
        return False
    try:
        r = _git(["rev-parse", "--show-toplevel"], d)
    except (subprocess.TimeoutExpired, OSError):
        return False
    if r.returncode != 0 or not r.stdout.strip():
        return False
    # git は実パスを返す（macOS の /var → /private/var 等）ので両辺を実パスで比べる
    top, rp = os.path.realpath(r.stdout.strip()), os.path.realpath(p)
    wt = os.path.realpath(WORKTREES_PREFIX)
    return top.startswith(wt + "/") and rp.startswith(top + "/")


def rule_worktree_guard(command: str):
    root = WORKTREES_PREFIX.rstrip("/")
    cwd0 = os.path.normpath(_CWD) if _CWD else ""
    cwd_in_wt = bool(cwd0) and _under_worktrees(cwd0)
    if ".worktrees" not in command and "worktree" not in command and not cwd_in_wt:
        return None  # 高速素通し
    # 相対パス・変数の行き先が分からないとき、worktree を巻き込みうる文脈かどうか
    risky_unknown = ".worktrees" in command or cwd0 == root
    targets = []   # (表示名, 絶対パス or None=判定不能)
    for cmd in _commands(command):
        tokens = cmd.tokens
        if not tokens or _marker(cmd, "WORKTREE_RM_OK"):
            continue
        base = os.path.basename(tokens[0])
        if base == "git":
            gcwd, sub, subargs = _git_parse(tokens, cmd.cwd, cmd.assigns)
            if sub == "worktree" and subargs[:1] == ["remove"]:
                for t in (a for a in subargs[1:] if not a.startswith("-")):
                    v = _resolved_value(t, cmd.assigns)
                    if v is not None and not os.path.isabs(v):
                        v = os.path.join(gcwd, v) if gcwd else None
                    targets.append((t, os.path.normpath(v) if v else None))
            continue
        starts = _find_delete_starts(tokens)
        if starts is not None:
            paths = starts
        elif base == "trash" or (base == "rm" and _is_recursive_rm(tokens)):
            paths = [t for t in tokens[1:] if not t.startswith("-")]
        else:
            continue
        if cmd.xargs and (risky_unknown or cwd_in_wt):
            targets.append(("(xargs の入力)", None))
        for t in paths:
            v = _resolved_value(t.strip('"').strip("'"), cmd.assigns)
            if v is None:
                if risky_unknown:
                    targets.append((t, None))
                continue
            if os.path.isabs(v):
                exp = os.path.normpath(v)
                if _under_worktrees(exp):
                    targets.append((t, exp))
                continue
            # 相対パス: 実行される cwd で解決する（`cd ~/.worktrees && rm -rf name` 等）。
            # worktree の中のサブパス（build/ 等の掃除）は対象外
            if cmd.cwd is None:
                if risky_unknown:
                    targets.append((t, None))
                continue
            exp = os.path.normpath(os.path.join(cmd.cwd, v))
            if _under_worktrees(exp) and not _inside_worktree(exp):
                targets.append((t, exp))
    bad = [t for t, p in targets if p is None or _worktree_state(p) != "merged_clean"]
    if not bad:
        return None
    return deny(
        f"🛑 worktree-guard: 未マージか判定不能の worktree を削除しようとしている: {', '.join(bad[:3])}\n"
        "未マージ worktree の削除は禁止(未回収の作業が消える)。main 取り込み済みなら自動で通る。"
        "本当に消すならユーザー明示OKを取り、削除コマンド自身の先頭に `WORKTREE_RM_OK=1 ` を付けて再実行"
        "（例: `WORKTREE_RM_OK=1 git worktree remove <path>`）。"
    )


# ---------------------------------------------------------- gh-comments-guard
def rule_gh_comments_guard(command: str):
    if "--comments" not in command:
        return None  # 高速素通し
    for seg in _split_segments(command):
        try:
            tokens = shlex.split(seg)
        except ValueError:
            continue
        while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
            tokens.pop(0)
        if not tokens or os.path.basename(tokens[0]) != "gh":
            continue
        sub = [t for t in tokens[1:] if not t.startswith("-")]
        if len(sub) >= 2 and sub[0] == "issue" and sub[1] == "view" and "--comments" in tokens \
                and not any(t == "--json" or t.startswith("--json=") for t in tokens):
            return deny(
                "🛑 gh-comments-guard: `gh issue view --comments` はコメント0件の issue で本文ごと空出力+exit 0"
                "(gh 2.96.0 実測)。`--json title,body,comments` 形を使うこと。"
            )
    return None


# ------------------------------------------------------------ pip-freeze-guard
def rule_pip_freeze_guard(command: str):
    if "freeze" not in command:
        return None  # 高速素通し
    for cmd in _commands(command):
        tokens = cmd.tokens
        if _marker(cmd, "PIP_FREEZE_OK"):
            continue
        if len(tokens) >= 2 and os.path.basename(tokens[0]) in ("pip", "pip3") and tokens[1] == "freeze":
            return deny(
                "🛑 pip-freeze-guard: uv 製 venv には pip が無く `pip freeze` は無言で0件を返す(空の退避ファイル事故)。"
                "`uv pip freeze` を使うこと。素の pip 環境で意図的なら `PIP_FREEZE_OK=1 ` を先頭に。"
            )
    return None


# ----------------------------------------------------------- shared-venv-guard
def rule_shared_venv_guard(command: str):
    if ".venvs" not in command:
        return None  # 高速素通し（共有 venv ~/.venvs/ に言及しないコマンドは対象外）
    for cmd in _commands(command):
        tk = cmd.tokens
        if _marker(cmd, "SHARED_VENV_OK") or len(tk) < 3:
            continue
        if os.path.basename(tk[0]) == "uv" and tk[1] == "pip" and \
                (tk[2] in ("sync", "uninstall") or (tk[2] == "install" and "--exact" in tk)):
            return deny(
                "🛑 shared-venv-guard: 共有 venv(~/.venvs/) への sync / --exact / uninstall は"
                "定義に無い同居パッケージを消す。install(追加のみ)を使うか、"
                "影響確認済みなら `SHARED_VENV_OK=1 ` を先頭に。"
            )
    return None


RULES = [
    rule_worktree_guard,      # rm-guard より先(SAFE_PREFIXES が ~/.worktrees/ を素通しするため)
    rule_merge_gate,
    rule_rm_guard,
    rule_push_freshness,
    rule_main_commit_freshness,
    rule_gh_comments_guard,
    rule_pip_freeze_guard,
    rule_shared_venv_guard,
]


_PERMISSION_MODE = ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    global _CWD, _PERMISSION_MODE
    _CWD = data.get("cwd") or os.getcwd()
    _PERMISSION_MODE = data.get("permission_mode") or ""
    command = (data.get("tool_input") or {}).get("command", "")
    # deny は ask より強い。ask を返したルールがあっても残りのルールを評価し、
    # どれかが deny なら deny を返す（マージと危険な操作を1行につないだものを ask で通さない）。
    pending_ask = None
    for rule in RULES:
        try:
            result = rule(command)
        except Exception as e:  # noqa: BLE001
            # hook の異常終了は「許可」扱いになるので、自分のバグでは安全側（確認）に倒す
            msg = (f"⚠️ bash-guard: ルール {rule.__name__} の評価中に例外 "
                   f"({type(e).__name__}: {e})。安全側に倒す（確認 or 拒否）。")
            result = deny(msg) if _PERMISSION_MODE == "bypassPermissions" else ask(msg)
        if not result:
            continue
        decision = result.get("hookSpecificOutput", {}).get("permissionDecision")
        if decision == "ask":
            pending_ask = pending_ask or result
            continue
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    if pending_ask:
        print(json.dumps(pending_ask, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
