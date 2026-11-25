#!/bin/bash
# Checks for skills/issue-ops/scripts/stale_body_check.py. A fake gh on PATH serves the fixture issues, so nothing
# reaches GitHub.
#   fixtures/stale-body/issues.json: #13 heading left on the previous year and round (the observed failure),
#   #14 the corrected body that mentions the previous round further down (must not fire), #15 an old "as of" date.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../skills/issue-ops/scripts/stale_body_check.py"
FIX="$HERE/fixtures/stale-body/issues.json"
T=$(mktemp -d "${TMPDIR:-/tmp}/stale-body.XXXX")
trap 'rm -rf "$T"' EXIT

# fake gh: prints the fixture for `gh issue list ... --repo example-org/example-repo`; exits 1 for any other repo
cat >"$T/gh" <<EOF
#!/bin/sh
case "\$*" in *"--repo example-org/example-repo"*) cat "$FIX" ;; *) echo "not found" >&2; exit 1 ;; esac
EOF
chmod +x "$T/gh"
run() { PATH="$T:$PATH" python3 "$SCRIPT" "$@"; }

echo '=== title and heading name different years and rounds ==='
OUT=$(run measure --repos example-org/example-repo --show --json); CODE=$?
[ "$CODE" = 0 ] && r=ok || r=ng; echo "  exit $CODE -> $r (expect ok)"
python3 - "$OUT" <<'PY' || exit 1
import json, sys
d = json.loads(sys.argv[1])
a = [h["number"] for h in d["hits"] if any(r.startswith("A:") for r in h["reasons"])]
b = [h["number"] for h in d["hits"] if any(r.startswith("B:") for r in h["reasons"])]
print(f"  scanned -> {d['scanned']} (expect 3)")
print(f"  check A suspects -> {len(a)} (expect 1)")
print(f"  check A suspect -> #{a[0] if a else 'none'} (expect #13)")
print(f"  corrected body #14 flagged -> {'yes' if 14 in a + b else 'no'} (expect no)")
print(f"  check B suspects -> {','.join(map(str, b)) or 'none'} (expect 15)")
PY

echo '=== a repo that cannot be listed is an error, not zero issues ==='
run measure --repos example-org/missing >/dev/null 2>&1; CODE=$?
[ "$CODE" = 1 ] && r=ok || r=ng; echo "  exit $CODE -> $r (expect ok: 1)"

echo '=== gh that hangs is an error, not zero issues ==='
# prints the real output of a repo with no open issues, then hangs: without the timeout it would report 0 and exit 0
python3 - "$SCRIPT" "$T" <<'PY' || exit 1
import contextlib, importlib.util, io, json, os, sys
script, tmp = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("stale_body_check", script)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
mod.GH_TIMEOUT = 0.5
hang = os.path.join(tmp, "hang"); os.makedirs(hang)
with open(os.path.join(hang, "gh"), "w") as f:
    f.write("#!/bin/sh\necho '[]'\nexec sleep 5\n")
os.chmod(os.path.join(hang, "gh"), 0o755)
os.environ["PATH"] = hang + os.pathsep + os.environ["PATH"]
sys.argv = ["stale_body_check.py", "measure", "--repos", "example-org/example-repo", "--json"]
out = io.StringIO()
with contextlib.redirect_stdout(out):
    rc = mod.main()
print(f"  exit -> {rc} (expect 1)")
print(f"  errors -> {len(json.loads(out.getvalue())['errors'])} (expect 1)")
PY

echo '=== the same number written with a leading zero is the same round ==='
python3 - "$SCRIPT" <<'PY' || exit 1
import importlib.util, sys
spec = importlib.util.spec_from_file_location("stale_body_check", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
r = mod.check_token_mismatch("令和8年度 第1回 申請", "令和8年度 第01回 申請")
print(f"  title 第1回, heading 第01回: reasons -> {len(r)} (expect 0)")
r = mod.check_token_mismatch("令和8年度 第1回 申請", "令和8年度 第02回 申請")
print(f"  title 第1回, heading 第02回: reasons -> {len(r)} (expect 1)")
PY

echo '=== the script never writes to GitHub ==='
n=$(grep -cE '"(create|edit|close|comment|delete|reopen|transfer|lock|pin)"|--method|-X *(POST|PATCH|PUT|DELETE)|"api"' "$SCRIPT")
[ "$n" = 0 ] && r=ok || r=ng; echo "  write calls: $n -> $r (expect ok)"
