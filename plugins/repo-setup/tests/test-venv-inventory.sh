#!/bin/bash
# Measures python-venv's venv_inventory.py on fake venvs in a temp dir. Expected values come from the skill text
# (SKILL.md, "Find dead venvs") and the script's docstring: a venv is a directory with a pyvenv.cfg; created is the
# pyvenv.cfg mtime; last modified is the newest mtime inside; likely dead = stalled (last change within the stall
# minutes of creation) and stale (no change for the stale days); node_modules, .git and Library/Caches are skipped;
# the run is read-only and exits 0. HOME points into the temp dir, so the default roots never scan the real home.
set -u
INV="$(cd "$(dirname "$0")/.." && pwd)/skills/python-venv/scripts/venv_inventory.py"
TMP=$(mktemp -d) || exit 1; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"
row() {  # row <description> <got> <want>: the verdict is ok when got equals want (run-all.sh reads lowercase words after ->)
  if [ "$2" = "$3" ]; then printf '  %-62s -> ok (expect ok)\n' "$1"; else printf '  %s [got: %s, want: %s] -> bad (expect ok)\n' "$1" "$2" "$3"; fi
}
DAY=86400
# venv <dir> <created-seconds-ago> <last-change-seconds-ago>: a fake venv whose pyvenv.cfg is <created> old
# and whose newest entry (a site-packages file) is <last-change> old; every other entry is as old as pyvenv.cfg
venv() {
  mkdir -p "$1/bin" "$1/lib/python3.12/site-packages/pkg"
  echo 'home = /usr/bin' > "$1/pyvenv.cfg"
  echo 'x' > "$1/bin/python"; echo 'print(1)' > "$1/lib/python3.12/site-packages/pkg/__init__.py"
  python3 - "$1" "$2" "$3" <<'PY'
import os, sys, time
root, created, last = sys.argv[1], time.time() - float(sys.argv[2]), time.time() - float(sys.argv[3])
for d, dirs, files in os.walk(root):
    for n in dirs + files:
        os.utime(os.path.join(d, n), (created, created))
os.utime(os.path.join(root, "lib/python3.12/site-packages/pkg/__init__.py"), (last, last))
os.utime(root, (created, created))
PY
}
# field <json> <venv path suffix> <key>: that venv's value, or "missing" when the venv is not listed
field() {
  python3 -c 'import json,sys
d=json.load(open(sys.argv[1])); m=[v for v in d["venvs"] if v["path"].endswith(sys.argv[2])]
print(json.dumps(m[0][sys.argv[3]]) if m else "missing")' "$1" "$2" "$3"
}
count() { python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["venvs"]))' "$1"; }
listing() { (cd "$1" && find . -exec stat -f '%N %z %m' {} + 2>/dev/null || find . -exec stat -c '%n %s %Y' {} +) | LC_ALL=C sort; }

S="$TMP/scan"
venv "$S/dead"            $((60*DAY))        $((60*DAY - 120))      # stalled 2 min after creation, untouched 60 days
venv "$S/new-stalled"     $((2*DAY))         $((2*DAY - 60))        # stalled, but only 2 days old
venv "$S/old-used"        $((90*DAY))        $((40*DAY))            # untouched 40 days, but used for 50 days after creation
mkdir -p "$S/repo"; touch "$S/repo/requirements-dev.txt"
venv "$S/repo/.venv"      $((60*DAY))        $((60*DAY))
venv "$S/node_modules/pkg/.venv" $((60*DAY)) $((60*DAY))
venv "$S/proj/.git/venv"  $((60*DAY))        $((60*DAY))
venv "$S/Library/Caches/tool/venv" $((60*DAY)) $((60*DAY))
venv "$S/outer"           $DAY               $DAY
venv "$S/outer/lib/inner" $((60*DAY))        $((60*DAY))            # a venv inside a venv is not looked for
venv "$S/a/b/c/d/e/f/g/deep" $((60*DAY))     $((60*DAY))            # depth 8 below the root
ln -s "$S/dead" "$S/link-to-dead"
listing "$S" > "$TMP/before"

python3 "$INV" "$S" --json > "$TMP/out.json" 2> "$TMP/err"; rc=$?
echo '=== flags (defaults: stall 10 min, stale 30 days) ==='
row 'exit status' "$rc" '0'
row 'stalled and untouched for 60 days is likely dead' "$(field "$TMP/out.json" /dead likely_dead)" 'true'
row 'stalled but 2 days old is not likely dead' "$(field "$TMP/out.json" /new-stalled likely_dead)" 'false'
row 'untouched 40 days but used after creation is not likely dead' "$(field "$TMP/out.json" /old-used likely_dead)" 'false'
row 'last_modified comes from the newest entry inside, not the root' "$(field "$TMP/out.json" /old-used stalled)" 'false'
row '--stale-days 1 makes the 2-day-old stalled venv likely dead' \
  "$(python3 "$INV" "$S" --json --stale-days 1 > "$TMP/s1.json"; field "$TMP/s1.json" /new-stalled likely_dead)" 'true'
row '--stall-minutes 1 makes the venv stalled after 2 minutes alive' \
  "$(python3 "$INV" "$S" --json --stall-minutes 1 > "$TMP/m1.json"; field "$TMP/m1.json" /dead likely_dead)" 'false'

echo '=== what is listed ==='
row 'node_modules is skipped' "$(field "$TMP/out.json" /node_modules/pkg/.venv path)" 'missing'
row '.git is skipped' "$(field "$TMP/out.json" /.git/venv path)" 'missing'
row 'Library/Caches is skipped' "$(field "$TMP/out.json" /Library/Caches/tool/venv path)" 'missing'
row 'a venv inside a venv is not listed' "$(field "$TMP/out.json" /outer/lib/inner path)" 'missing'
row 'a symlink to a venv is not followed' "$(field "$TMP/out.json" /link-to-dead path)" 'missing'
row 'deeper than the default --max-depth 6 is not listed' "$(field "$TMP/out.json" /deep path)" 'missing'
row '--max-depth 8 lists it' "$(python3 "$INV" "$S" --json --max-depth 8 > "$TMP/d8.json"; field "$TMP/d8.json" /deep likely_dead)" 'true'
row 'exactly the five venvs are listed' "$(count "$TMP/out.json")" '5'
row 'a requirements*.txt next to the venv is reported' "$(field "$TMP/out.json" /repo/.venv deps_files)" '["requirements-dev.txt"]'
row 'no deps file reports an empty list' "$(field "$TMP/out.json" /dead deps_files)" '[]'

echo '=== JSON shape ==='
row 'top-level keys' "$(python3 -c 'import json,sys; print(",".join(sorted(json.load(open(sys.argv[1])))))' "$TMP/out.json")" 'generated_at,roots,thresholds,venvs'
row 'per-venv keys' "$(python3 -c 'import json,sys; print(",".join(sorted(json.load(open(sys.argv[1]))["venvs"][0])))' "$TMP/out.json")" \
  'created,deps_files,idle_days,last_modified,likely_dead,path,size_bytes,stale,stalled'
row 'size_bytes counts the files inside' "$(field "$TMP/out.json" /new-stalled size_bytes)" '27'
row 'created is the pyvenv.cfg mtime (ISO date 60 days ago)' "$(field "$TMP/out.json" /repo/.venv created | cut -c2-11)" \
  "$(python3 -c 'import datetime,time; print(datetime.datetime.fromtimestamp(time.time()-60*86400).strftime("%Y-%m-%d"))')"
row 'nothing on stderr' "$(wc -c < "$TMP/err" | tr -d ' ')" '0'

echo '=== read-only ==='
python3 "$INV" "$S" > /dev/null 2>&1
listing "$S" > "$TMP/after"
row 'path, size and mtime of every entry are unchanged after runs' "$(cmp -s "$TMP/before" "$TMP/after" && echo same || echo changed)" 'same'

echo '=== roots ==='
venv "$HOME/.venvs/cad" $DAY $DAY
venv "$HOME/work/app/.venv" $DAY $DAY
python3 "$INV" --json > "$TMP/home.json" 2>/dev/null
row 'no root scans the shared dir and ~, listing each venv once' "$(count "$TMP/home.json")" '2'
row '--shared-dir is scanned when no root is given' \
  "$(python3 "$INV" --json --shared-dir "$S" > "$TMP/sd.json" 2>/dev/null; field "$TMP/sd.json" /new-stalled likely_dead)" 'false'
out=$(python3 "$INV" "$TMP/missing" --json 2> "$TMP/err"); rc=$?
row 'a missing root exits 0' "$rc" '0'
row 'and warns on stderr' "$([ -s "$TMP/err" ] && echo yes || echo no)" 'yes'
row 'and stdout is still JSON with no venvs' "$(printf '%s' "$out" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["venvs"]))')" '0'
row 'the table ends with a totals line' "$(python3 "$INV" "$S" | tail -1 | sed 's/, [0-9.]*[BKMG];/;/; s/, [0-9.]*[BKMG]$//')" '5 venvs; 2 likely dead'
