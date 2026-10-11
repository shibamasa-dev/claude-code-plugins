#!/usr/bin/env python3
"""Validate the reviewer's findings. A finding whose quote is not contained verbatim in that line is dropped as invalid.

  python3 validate_findings.py <skill directory> [reviewer output file | -]

Input is the reviewer's raw output (a bare JSON array, one inside a ```json fence, or one surrounded by prose).
Output (stdout, JSON): {"valid": [...], "invalid": [{..., "reason": ...}], "invalid_ratio": x}
exit 0 = parsed / 2 = no JSON array could be extracted.
"""
import json, os, re, sys

FIELDS = ("file", "line", "quote", "category", "fix", "confidence")


def extract_array(text):
    """Extract a JSON array from the reviewer output. Tries the whole text, then ```json fences, then the first [ to the last ]."""
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
            reason = "missing required fields (%s)" % ", ".join(FIELDS)
        else:
            ab = os.path.abspath(os.path.join(root, os.path.expanduser(str(f["file"]))))
            rel = os.path.relpath(ab, root).replace(os.sep, "/")
            quote = str(f["quote"])
            try:
                line = int(f["line"])
            except (TypeError, ValueError):
                line = -1
            if not ab.startswith(root + os.sep) or not os.path.isfile(ab):
                reason = "no such file"
            elif not quote.strip():
                reason = "empty quote"
            else:
                if ab not in cache:
                    cache[ab] = open(ab, encoding="utf-8", errors="replace").read().splitlines()
                lines = cache[ab]
                if line == 0:
                    reason = None if quote in rel else "line 0 (file level) but the quote is not part of the path"
                elif not 1 <= line <= len(lines):
                    reason = "line number out of range"
                elif quote not in lines[line - 1]:
                    reason = "quote is not contained verbatim in that line"
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
        print(json.dumps({"error": "cannot extract a JSON array"}, ensure_ascii=False))
        sys.exit(2)
    json.dump(validate(sys.argv[1], arr), sys.stdout, ensure_ascii=False, indent=1)
    print()


if __name__ == "__main__":
    main()
