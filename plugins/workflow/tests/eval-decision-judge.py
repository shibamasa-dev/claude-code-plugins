#!/usr/bin/env python3
"""Score decision-capture's judge (hooks/_decision_judge.py) against a hand-labelled dataset.

    python3 tests/eval-decision-judge.py [--dataset FILE] [--backends regex,openai,typesafe,google] [--json]

The default dataset is tests/fixtures/decision-capture/ask_dataset.json (label = does the reply ask the user to decide).
For each backend it prints caught asks (recall), false positives at the default threshold, and a threshold sweep.
A model backend is sent only the replies that pass the same pre-filter as in the hook (maybe_asks); the rest score 0.
Keys come from OPENAI_DECISIONS_API_KEY, TYPESAFE_API_KEY and GEMINI_API_KEY; a backend without its key, or an item
whose call failed, is counted as "not measured" and never mixed into that backend's numbers.
Model backends cost money and send the dataset's text to the vendor, so this is not part of tests/run-all.sh.
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "hooks"))
import _decision_judge as J  # noqa: E402

DATASET = HERE / "fixtures" / "decision-capture" / "ask_dataset.json"
KEY_ENV = {"openai": "OPENAI_DECISIONS_API_KEY", "typesafe": "TYPESAFE_API_KEY", "google": "GEMINI_API_KEY"}
SWEEP = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97, 0.98)


def scores(backend, items, timeout):
    """id -> score (None when not measured)."""
    out = {}
    key = os.environ.get(KEY_ENV.get(backend, ""), "")
    for it in items:
        text = it["text"]
        if backend == "regex":
            out[it["id"]] = J.regex_asks(text).score
        elif not J.maybe_asks(text):
            out[it["id"]] = 0.0
        elif not key:
            out[it["id"]] = None
        else:
            try:
                out[it["id"]] = J.SCORERS[backend](text, key, timeout)
            except J.JudgeError:
                out[it["id"]] = None
    return out


def tally(items, sc, threshold):
    pos = [it for it in items if sc[it["id"]] is not None]
    caught = [it["id"] for it in pos if it["label"] and sc[it["id"]] >= threshold]
    fp = [it["id"] for it in pos if not it["label"] and sc[it["id"]] >= threshold]
    return {"asks": sum(1 for it in pos if it["label"]), "caught": len(caught),
            "not_asks": sum(1 for it in pos if not it["label"]), "false_positives": len(fp),
            "missed": [it["id"] for it in pos if it["label"] and sc[it["id"]] < threshold], "fp_ids": fp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=DATASET)
    ap.add_argument("--backends", default="regex")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds per call (the hook uses 2)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    items = json.loads(args.dataset.read_text())["items"]
    report = {}
    for b in args.backends.split(","):
        b = b.strip()
        if b not in J.BACKENDS:
            print(f"unknown backend {b!r}", file=sys.stderr)
            return 2
        sc = scores(b, items, args.timeout)
        unmeasured = [i for i, v in sc.items() if v is None]
        default = 0.5 if b == "regex" else J.THRESHOLDS[b]
        entry = {"items": len(items), "not_measured": len(unmeasured), "threshold": default,
                 "at_threshold": tally(items, sc, default)}
        if b != "regex":
            entry["sweep"] = {str(t): {k: v for k, v in tally(items, sc, t).items() if k in ("caught", "false_positives")}
                              for t in SWEEP}
        report[b] = entry
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        for b, e in report.items():
            t = e["at_threshold"]
            print(f"{b}: caught {t['caught']}/{t['asks']} asks, {t['false_positives']}/{t['not_asks']} false positives "
                  f"at {e['threshold']} ({e['not_measured']} of {e['items']} not measured); missed {t['missed']}")
            for th, r in (e.get("sweep") or {}).items():
                print(f"    >= {th}: caught {r['caught']}, false positives {r['false_positives']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
