#!/usr/bin/env python3
"""グループ A（決定論）: lint.py をフィクスチャに流し、evals/evals.json の期待カテゴリと突き合わせる。

  python3 scripts/run_evals.py [ケース ID ...]

採点: 陽性は lint_expect ⊆ その行で出たカテゴリ（lint_expect_match があれば、その文字列を含む match も要る）、陰性・陽性とも lint_forbid ∩ 出たカテゴリ = ∅。
行は file と anchor（行内の一意な断片）で特定する。anchor が無いケースは line 0（ファイル単位の指摘）。
フィクスチャのうち 2 行は、公開リポの漏れ検査（ホームの絶対パス・メールアドレス）に当たる部分を
トークン（{{USERS_DIR}}・{{AT}}）にして置いてある。materialize() が一時ディレクトリへ展開してから流すので、
lint が見る行は逐語どおり。展開済みのファイルはリポ内に残さない。
exit 0 = 全件 PASS / 1 = FAIL あり。
"""
import contextlib, json, os, shutil, sys, tempfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
import lint  # noqa: E402


# 検査に当たる文字列をこのファイルにも素で書かない（連結して組み立てる）
TOKENS = {"{{USERS_DIR}}": "/" + "Us" + "ers/", "{{AT}}": "@"}


@contextlib.contextmanager
def materialize(src):
    """フィクスチャを一時ディレクトリにコピーしてトークンを展開し、そのパスを返す。抜けたら消す。"""
    tmp = tempfile.mkdtemp(prefix="skill-lint-fixture-")
    dst = os.path.join(tmp, os.path.basename(src))
    try:
        shutil.copytree(src, dst)
        for d, _, files in os.walk(dst):
            for f in files:
                p = os.path.join(d, f)
                s = open(p, encoding="utf-8").read()
                for k, v in TOKENS.items():
                    s = s.replace(k, v)
                open(p, "w", encoding="utf-8").write(s)
        yield dst
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def locate(fixture, case):
    """anchor を含む行番号を返す。見つからない・複数なら None。"""
    if case.get("anchor") is None:
        return 0 if os.path.exists(os.path.join(fixture, case["file"])) else None
    lines = open(os.path.join(fixture, case["file"]), encoding="utf-8").read().splitlines()
    hits = [i for i, l in enumerate(lines, 1) if case["anchor"] in l]
    return hits[0] if len(hits) == 1 else None


def main():
    spec = json.load(open(os.path.join(SKILL_DIR, "evals", "evals.json"), encoding="utf-8"))
    with materialize(os.path.join(SKILL_DIR, spec["fixture_dir"])) as fixture:
        ok = grade(spec, fixture, set(sys.argv[1:]))
    sys.exit(0 if ok else 1)


def grade(spec, fixture, only):
    res = lint.lint(fixture, use_gitleaks=False)
    passed = failed = 0
    for c in spec["cases"]:
        if only and c["id"] not in only:
            continue
        line = locate(fixture, c)
        if line is None:
            failed += 1
            print("FAIL %s: フィクスチャの行が特定できない（%s / %r）" % (c["id"], c["file"], c.get("anchor")))
            continue
        got = sorted({f["category"] for f in res["findings"] if f["file"] == c["file"] and f["line"] == line})
        matches = [f["match"] for f in res["findings"] if f["file"] == c["file"] and f["line"] == line]
        missing = [x for x in c["lint_expect"] if x not in got]
        missing += ["match:" + m for m in c.get("lint_expect_match", []) if not any(m in x for x in matches)]
        forbidden = [x for x in c["lint_forbid"] if x in got]
        ok = not missing and not forbidden
        passed += ok
        failed += not ok
        detail = "期待 %s / 実測 %s" % (c["lint_expect"] or "なし", got or "なし")
        if missing:
            detail += " / 欠落 %s" % missing
        if forbidden:
            detail += " / 禁止 %s" % forbidden
        print("%s %s (%s:%d): %s" % ("PASS" if ok else "FAIL", c["id"], c["file"], line, detail))
    total = passed + failed
    print("\npass_rate: %d/%d = %.2f" % (passed, total, passed / total if total else 0))
    return failed == 0 and total > 0


if __name__ == "__main__":
    main()
