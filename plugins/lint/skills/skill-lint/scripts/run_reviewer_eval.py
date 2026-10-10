#!/usr/bin/env python3
"""グループ B（reviewer）: references/reviewer-prompt.md を `claude -p` に渡してフィクスチャをレビューさせ、
validate_findings.py で quote を検証してから、reviewer だけが拾える陽性の recall と陰性への誤検知を数える。

  python3 scripts/run_reviewer_eval.py [--runs 1] [--workers 3] [--timeout 600] [--keep DIR]

モデルは指定しない（claude の既定）。フィクスチャの内容は行番号つきで prompt に入れ、ヒントとして
lint.py の結果を添える。フィクスチャの作者はこの実行環境の人ではないので、reviewer-prompt の
「実行環境から固有名のヒントを集める」手順はこの評価では行わせない（固有名は本文だけから判定させる）。
採点: 陽性の reviewer_expect の各要素（期待する指摘 1 件）は、同じ file・line に、要素内の語のどれかを
quote に含む有効な指摘があれば命中。
陰性は同じ行への有効な指摘を誤検知に数える（reviewer_forbid_quote があるケースは quote がそれを含むものだけ）。
合格の目安: recall ≥ 0.8 かつ各回の誤検知 ≤ 1。exit 0 = 目安を満たす / 1 = 満たさない。
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
import lint  # noqa: E402
import validate_findings as vf  # noqa: E402
from run_evals import locate, materialize  # noqa: E402


def build_prompt(fixture):
    parts = [open(os.path.join(SKILL_DIR, "references", "reviewer-prompt.md"), encoding="utf-8").read()]
    parts.append("\n## 対象スキル（ファイル内容・行番号つき。ツールは使わずこれを読む）\n")
    for rel, ab, _ in lint.iter_files(fixture):
        text = lint.read_text(ab)
        if text is None:
            continue
        parts.append("### %s\n```" % rel)
        parts += ["%d: %s" % (i, l) for i, l in enumerate(text.splitlines(), 1)]
        parts.append("```")
    res = lint.lint(fixture, use_gitleaks=False)
    hints = [{k: f[k] for k in ("file", "line", "category", "match")} for f in res["findings"]]
    parts.append("\n## ヒント: linter の結果\n```json\n%s\n```" % json.dumps(hints, ensure_ascii=False))
    parts.append("\n## 実行環境のヒント\nこの評価では実行環境からヒントを集めない（コマンドは実行しない）。固有名は対象スキルの本文だけから判定する。")
    parts.append("\n上の指示どおり、JSON 配列だけを出力してください。")
    return "\n".join(parts)


def run_claude(prompt, timeout):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    cwd = tempfile.mkdtemp(prefix="skill-lint-eval-")  # 空の cwd: プロジェクトの CLAUDE.md を読ませない
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--max-turns", "5"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "seconds": timeout}
    out = {"seconds": round(time.time() - t0, 1), "returncode": r.returncode}
    try:
        j = json.loads(r.stdout)
        out["result"] = j.get("result", "")
        out["model"] = ",".join((j.get("modelUsage") or {}).keys()) or j.get("model", "")
    except ValueError:
        out["result"] = r.stdout
        out["stderr"] = r.stderr[-500:]
    return out


def score(spec, fixture, valid):
    pos_hits, pos_total, fps = [], 0, []
    for c in spec["cases"]:
        line = locate(fixture, c)
        at = [f for f in valid if f["file"] == c["file"] and f["line"] == line]
        if c["kind"] == "positive":
            for n, group in enumerate(c.get("reviewer_expect", []), 1):
                pos_total += 1
                if any(any(k in f["quote"] for k in group) for f in at):
                    pos_hits.append("%s-%d" % (c["id"], n))
        elif c["kind"] == "negative":
            if c.get("reviewer_forbid_quote"):
                at = [f for f in at if any(k in f["quote"] for k in c["reviewer_forbid_quote"])]
            fps += [{"case": c["id"], "quote": f["quote"], "category": f["category"]} for f in at]
    return pos_hits, pos_total, fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--keep", help="生出力と検証結果を保存するディレクトリ")
    a = ap.parse_args()
    spec = json.load(open(os.path.join(SKILL_DIR, "evals", "evals.json"), encoding="utf-8"))
    with materialize(os.path.join(SKILL_DIR, spec["fixture_dir"])) as fixture:
        ok = evaluate(spec, fixture, a)
    sys.exit(0 if ok else 1)


def evaluate(spec, fixture, a):
    prompt = build_prompt(fixture)
    with ThreadPoolExecutor(a.workers) as ex:
        outs = list(ex.map(lambda _: run_claude(prompt, a.timeout), range(a.runs)))
    keep = a.keep or tempfile.mkdtemp(prefix="skill-lint-eval-out-")
    os.makedirs(keep, exist_ok=True)
    hits_sum = total_sum = 0
    ok = True
    for i, o in enumerate(outs, 1):
        arr = vf.extract_array(o.get("result", "")) if "result" in o else None
        if arr is None:
            print("run %d: JSON 配列を取り出せない（%s）" % (i, o.get("error") or o.get("stderr") or o.get("result", "")[:200]))
            ok = False
            continue
        v = vf.validate(fixture, arr)
        hits, total, fps = score(spec, fixture, v["valid"])
        hits_sum += len(hits)
        total_sum += total
        ok &= len(fps) <= 1
        json.dump({"raw": o, "validated": v, "hits": hits, "false_positives": fps},
                  open(os.path.join(keep, "run%d.json" % i), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("run %d（%ss・model=%s）: recall %d/%d %s / 陰性誤検知 %d %s / 指摘 %d 件（有効 %d・無効 %d・無効比率 %.2f）" % (
            i, o.get("seconds"), o.get("model") or "既定", len(hits), total, hits, len(fps),
            [f["case"] + ":" + f["quote"] for f in fps], len(arr), len(v["valid"]), len(v["invalid"]), v["invalid_ratio"]))
        for x in v["invalid"]:
            print("    無効: %s:%s %r（%s）" % (x.get("file"), x.get("line"), x.get("quote"), x["reason"]))
    recall = hits_sum / total_sum if total_sum else 0.0
    ok &= recall >= 0.8 and total_sum > 0
    print("\n合計: recall %d/%d = %.2f（目安 ≥ 0.80）/ 各回の陰性誤検知 ≤ 1 / 結果: %s" % (
        hits_sum, total_sum, recall, "目安を満たす" if ok else "目安に届かない"))
    print("生出力: %s" % keep)
    return ok


if __name__ == "__main__":
    main()
