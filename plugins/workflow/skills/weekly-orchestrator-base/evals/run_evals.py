"""weekly-orchestrator-base の eval を手作業ゼロで回す（標準ライブラリのみ）。

  python3 evals/run_evals.py                          # 全ケース（直列）
  python3 evals/run_evals.py --jobs 3                 # ケースを 3 本並行
  python3 evals/run_evals.py --case 1 --case 4
  python3 evals/run_evals.py --grade-only <run_dir>   # 既存の回答を採点し直す

各ケースについて:
  1. executor: まっさらな `claude -p` に SKILL.md を読ませ、ドライランでプロンプトを解かせて answer.md に保存
  2. grader  : 別の `claude -p` が answer.md と assertions を突き合わせ grading.json を出す
  3. 集計    : pass_rate を表示し、run_dir/summary.json に書く

状況はすべて依頼文に書いた架空の設定（GitHub は見ない）。executor には Read/Glob/Grep しか渡さないので、
gh も書き込みも物理的にできない（ドライランを道具の制限で守る）。executor の cwd は空の一時ディレクトリにして、
どこかのプロジェクトの CLAUDE.md やスキルが混ざらないようにする。
executor と grader を別プロセスに分けるのは、書いた本人に採点させないため。

元はプロジェクト版 weekly-orchestrator の run_evals.py。依存: claude CLI（PATH）。
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SKILL = Path(__file__).resolve().parent.parent          # .../skills/weekly-orchestrator-base
EVALS = SKILL / "evals"
TOOLS = "Read,Glob,Grep"
GRADER_TOOLS = "Read,Write"
MAIN = (1, 2, 3, 4)

EXECUTOR = """あなたは、あるプロジェクトの週次オーケストレータ agent です。次のスキルを読んで、その所作どおりに依頼へ答えてください。

スキル本体: {skill}/SKILL.md（references/ も同じディレクトリ）

## これはドライランです
- 依頼文の状況は架空の設定です。GitHub・セッション一覧などの実物は見ず、依頼文に書いた状態だけで答える
- issue の作成・編集・close、PR 操作、subagent・spawn_task・別セッションの起動、SendMessage、archive_session、
  ファイルの作成・編集は**しない**。代わりに「実際なら何を・どの内容で・どの順で実行するか」を回答に書く
- ユーザーへの確認が要る場面では、確認する内容を回答に書き、そこで止まるべきか先へ進めてよいかをスキルに従って判断して書く
- 今日は {today}

## 依頼
{prompt}

## 出力
スキルの所作に沿って、最終的な回答（判断と理由・実行する操作・書き込む内容・プロンプト）を1つのまとまった文章で返してください。
"""

GRADER = """あなたは eval の採点者です。回答を読み、assertions を1つずつ PASS / FAIL で判定してください。

## 採点対象の回答
{answer_path}
（Read ツールで全文を読んでください）

## 期待される内容（参考。assertions より優先しない）
{expected}

## assertions
{assertions}

## 判定基準
- PASS: 回答の中に、その assertion が真だと分かる具体的な記述がある
- FAIL: 記述が無い / 矛盾する / 表面的にしか満たしていない（結論だけ合っていて根拠が無い等）
- 迷ったら FAIL。立証責任は assertion 側にある
- evidence には回答からの**引用**を入れる（要約でなく原文の一部）

## 出力
{out_path} に、次の形の JSON **だけ**を Write ツールで書いてください（前後に説明を足さない）。

{{
  "expectations": [
    {{"text": "<assertion の原文>", "passed": true, "evidence": "<回答からの引用>"}}
  ],
  "summary": {{"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0}}
}}
"""


def run_claude(prompt: str, cwd: Path, timeout: int, tools: str) -> str:
    """CLAUDECODE を外して claude -p を呼ぶ（Claude Code の中から入れ子で起動するため）。"""
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    p = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text", "--allowedTools", tools],
        # encoding を明示する。Windows の既定は CP932 で、claude の日本語回答は UTF-8
        cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
    )
    if p.returncode != 0:
        raise RuntimeError(f"claude -p が exit {p.returncode}: {p.stderr[-2000:]}")
    return p.stdout


def read_grading(path: Path, asserts: list[str]) -> list[dict]:
    """grading.json を読み、assertions と1対1で対応しているか確かめる。

    LLM の出力は非決定的で、7件中1件しか返さない・重複させる・passed を文字列で返す、が起こりうる。
    返ってきた配列だけで分母を作ると、1件しか採点しなくても 1/1 = 100% になって主要ケースが通ってしまう。
    照合に落ちたものは採点失敗として扱い、満点と区別する。
    """
    norm = lambda s: " ".join(str(s).split())
    g = json.loads(path.read_text(encoding="utf-8"))
    # 型を先に確かめてから .get() を呼ぶ（grader は JSON なら何でも書けるので、配列・文字列・null が来うる）
    if not isinstance(g, dict):
        raise ValueError(f"grading.json のルートがオブジェクトでない（{type(g).__name__}）")
    exps = g.get("expectations")
    if not isinstance(exps, list):
        raise ValueError("expectations が配列でない")
    if not all(isinstance(e, dict) for e in exps):
        raise ValueError("expectations にオブジェクト以外の項目がある")
    bad = [e for e in exps if not isinstance(e.get("passed"), bool)]
    if bad:
        raise ValueError(f"passed が boolean でない項目が {len(bad)} 件（例 {bad[0].get('text')!r}）")
    got, want = [norm(e.get("text")) for e in exps], [norm(a) for a in asserts]
    if sorted(got) != sorted(want):
        raise ValueError(f"assertions と一致しない（採点 {len(got)} 件 / 期待 {len(want)} 件）"
                         f"\n  採点されなかった: {[a for a in want if a not in got]}"
                         f"\n  余分: {[t for t in got if t not in want]}")
    return exps


def exit_code(results: list[tuple], selected: bool) -> int:
    """終了コード。results は [(case_id, 通った数, 総数)]、selected は --case を指定したか。

    --case を指定したら選んだケースそのもの、全ケース実行なら主要ケース（MAIN）で判定する。
    判定対象が空なら 1（「対象が無い＝成功」にしない）。
    """
    judged = results if selected else [r for r in results if r[0] in MAIN]
    return 0 if judged and all(o == n for _, o, n in judged) else 1


def run_case(c: dict, run_dir: Path, grade_only: bool, timeout: int) -> tuple[int, int, int, list[str]]:
    """1 ケースを回す。戻り値 (case_id, 通った数, 総数, 表示する行)。並行時に出力が混ざらないよう行は返す。"""
    log = []
    d = run_dir / f"case-{c['id']}"
    d.mkdir(parents=True, exist_ok=True)
    answer, grading = d / "answer.md", d / "grading.json"
    asserts = c.get("assertions") or c.get("expectations") or []

    if not grade_only:
        t0 = time.time()
        with tempfile.TemporaryDirectory(prefix="wob-eval-") as cwd:
            out = run_claude(EXECUTOR.format(skill=SKILL, prompt=c["prompt"], today=c["today"]),
                             Path(cwd), timeout, TOOLS)
        answer.write_text(out, encoding="utf-8")
        log.append(f"[case {c['id']}] executor {time.time()-t0:.0f}s -> {answer}")

    # 前回の採点結果を先に消す。残したままだと、grader が Write せず説明だけ返しても
    # 存在確認が通り、古い採点を今回の結果として集計してしまう
    grading.unlink(missing_ok=True)
    run_claude(GRADER.format(answer_path=answer, expected=c.get("expected_output", ""),
                             assertions="\n".join(f"{i+1}. {a}" for i, a in enumerate(asserts)),
                             out_path=grading), d, timeout, GRADER_TOOLS)
    if not grading.exists():
        log.append(f"[case {c['id']}] 採点失敗: grading.json が書かれなかった")
        return c["id"], 0, len(asserts), log
    try:
        exps = read_grading(grading, asserts)
    except (ValueError, json.JSONDecodeError) as e:
        log.append(f"[case {c['id']}] 採点失敗: {e}")
        return c["id"], 0, len(asserts), log
    g = json.loads(grading.read_text(encoding="utf-8"))
    ok = sum(1 for e in exps if e["passed"])
    # grader が summary を書き間違えても集計は expectations から取り直す
    g["summary"] = {"passed": ok, "failed": len(exps) - ok, "total": len(exps),
                    "pass_rate": round(ok / len(exps), 4) if exps else 0.0}
    grading.write_text(json.dumps(g, ensure_ascii=False, indent=1), encoding="utf-8")
    log += [f"    {'PASS' if e['passed'] else 'FAIL'}  {e['text']}" for e in exps]
    log.append(f"[case {c['id']}] {ok}/{len(exps)}")
    return c["id"], ok, len(exps), log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=int, action="append", help="回す eval の id（複数可・既定は全部）")
    ap.add_argument("--jobs", type=int, default=1, help="並行して回すケースの数（既定 1＝直列）")
    ap.add_argument("--timeout", type=int, default=1800, help="1ケースあたりの秒数")
    ap.add_argument("--grade-only", metavar="RUN_DIR", help="既存の run ディレクトリを採点し直す")
    args = ap.parse_args()

    cases = json.loads((EVALS / "evals.json").read_text(encoding="utf-8"))["evals"]
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
    if not cases:
        sys.exit("該当する eval が無い")

    run_dir = Path(args.grade_only).resolve() if args.grade_only else \
        EVALS / "runs" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"run: {run_dir}  cases: {[c['id'] for c in cases]}  jobs: {args.jobs}\n", flush=True)

    def one(c):
        try:
            return run_case(c, run_dir, bool(args.grade_only), args.timeout)
        except Exception as e:  # 1 ケースの失敗（timeout・exit≠0）で他のケースを止めない
            n = len(c.get("assertions") or c.get("expectations") or [])
            return c["id"], 0, n, [f"[case {c['id']}] 実行失敗: {e}"]

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        for cid, ok, n, log in ex.map(one, cases):
            print("\n".join(log) + "\n", flush=True)
            results.append((cid, ok, n))

    tot_ok = sum(r[1] for r in results)
    tot = sum(r[2] for r in results)
    print("=" * 60)
    for cid, ok, n in results:
        print(f"case {cid}: {ok}/{n}" + ("  ← 主要ケース" if cid in MAIN else ""))
    print(f"pass_rate {tot_ok}/{tot} = {tot_ok/tot:.1%}" if tot else "pass_rate 測定不能")
    (run_dir / "summary.json").write_text(json.dumps(
        {"run": run_dir.name,
         "cases": [{"id": c, "passed": o, "total": n} for c, o, n in results],
         "pass_rate": round(tot_ok / tot, 4) if tot else 0.0}, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(exit_code(results, bool(args.case)))


if __name__ == "__main__":
    main()
