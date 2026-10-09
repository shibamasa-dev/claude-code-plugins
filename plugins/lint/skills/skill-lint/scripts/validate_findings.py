#!/usr/bin/env python3
"""reviewer の指摘を検証する。quote がその行に逐語で含まれない指摘は無効として落とす。

  python3 validate_findings.py <スキルのディレクトリ> [reviewer の出力ファイル | -]

入力は reviewer の生出力（JSON 配列そのもの、```json フェンス入り、前後に文があるもの、のどれでもよい）。
出力（stdout・JSON）: {"valid": [...], "invalid": [{..., "reason": ...}], "invalid_ratio": x}
exit 0 = 読めた / 2 = JSON 配列を取り出せない。
"""
import json, os, re, sys

FIELDS = ("file", "line", "quote", "category", "fix", "confidence")


def extract_array(text):
    """reviewer の出力から JSON 配列を取り出す。全文 → ```json フェンス → 最初の [ 〜最後の ] の順。"""
    cands = [text.strip()]
    cands += re.findall(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    if "[" in text and "]" in text:
        cands.append(text[text.index("["):text.rindex("]") + 1])
    for c in cands:
        try:
            v = json.loads(c)
        except ValueError:
            continue
        if isinstance(v, list):
            return v
    return None


def validate(root, findings):
    root = os.path.abspath(os.path.expanduser(root))
    cache, valid, invalid = {}, [], []
    for f in findings:
        reason = None
        if not isinstance(f, dict) or any(k not in f for k in FIELDS):
            reason = "必須フィールドが無い（%s）" % ", ".join(FIELDS)
        else:
            ab = os.path.abspath(os.path.join(root, os.path.expanduser(str(f["file"]))))
            rel = os.path.relpath(ab, root).replace(os.sep, "/")
            quote = str(f["quote"])
            try:
                line = int(f["line"])
            except (TypeError, ValueError):
                line = -1
            if not ab.startswith(root + os.sep) or not os.path.isfile(ab):
                reason = "ファイルが無い"
            elif not quote.strip():
                reason = "quote が空"
            else:
                if ab not in cache:
                    cache[ab] = open(ab, encoding="utf-8", errors="replace").read().splitlines()
                lines = cache[ab]
                if line == 0:
                    reason = None if quote in rel else "line 0（ファイル単位）なのに quote がパスに含まれない"
                elif not 1 <= line <= len(lines):
                    reason = "行番号が範囲外"
                elif quote not in lines[line - 1]:
                    reason = "quote がその行に逐語で含まれない"
                f = dict(f, file=rel, line=line)
        if reason:
            invalid.append(dict(f, reason=reason) if isinstance(f, dict) else {"raw": f, "reason": reason})
        else:
            valid.append(f)
    n = len(valid) + len(invalid)
    return {"valid": valid, "invalid": invalid, "invalid_ratio": (len(invalid) / n) if n else 0.0}


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    src = sys.argv[2] if len(sys.argv) > 2 else "-"
    text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
    arr = extract_array(text)
    if arr is None:
        print(json.dumps({"error": "JSON 配列を取り出せない"}, ensure_ascii=False))
        sys.exit(2)
    json.dump(validate(sys.argv[1], arr), sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
