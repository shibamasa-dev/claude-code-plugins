#!/bin/bash
# weekly-orchestrator-base scripts: cycle.py (title, week, body, splice, boundary), create-cycle-issue.sh (what the
# weekly-issue workflow runs) and survey.py, against hand-written fixtures in fixtures/weekly-orchestrator/.
# The fixtures copy the shapes gh returns (GraphQL issues with subIssuesSummary / issueFieldValues, gh issue list,
# gh pr list) with a made-up repo (example-org/sample-app) and made-up values.
# Synthesized: gh is a fake on PATH that answers from the fixtures and records issue create / field mutations.
# Expected values come from SKILL.md and references/plan-section.md (title once, dedup by exact title, splice only
# the plan section and refuse a confirmed one, boundary order Tally start -> Cutoff/Submitted -> close time).
set -u
D="$(cd "$(dirname "$0")/.." && pwd)"
S="$D/skills/weekly-orchestrator-base/scripts"
FX="$D/tests/fixtures/weekly-orchestrator"
T=$(mktemp -d "${TMPDIR:-/tmp}/wo.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
unset GITHUB_REPOSITORY
row() { printf '  %s -> %s (expect %s)\n' "$1" "$2" "$3"; }
yes_no() { [ "$1" = "$2" ] && echo ok || echo "bad:$1"; }

mkdir -p "$T/bin" "$T/repo/.claude"
cp "$FX/config.json" "$T/repo/.claude/weekly-orchestrator.json"
git -C "$T/repo" init -q
cp "$FX/cycles-before.json" "$T/cycles.json"
cat > "$T/bin/gh" <<EOF
#!/bin/bash
# Fake gh: answers from the fixtures, logs writes to $T/log
case "\$1 \$2" in
  "api graphql") if printf '%s ' "\$@" | grep -q setIssueFieldValue; then echo "fields \$*" >> "$T/log"; echo '{}'; else cat "$FX/issues.json"; fi ;;
  "pr list") cat "$FX/prs.json" ;;
  "issue list") cat "$T/cycles.json" ;;
  "issue create") echo "create \$*" >> "$T/log"; echo "https://github.com/example-org/sample-app/issues/99" ;;
  "issue view") [ -f "$T/viewfail" ] && exit 1; echo '{"id":"I_fake99"}' ;;
  *) echo "fake gh: unexpected \$*" >&2; exit 1 ;;
esac
EOF
chmod +x "$T/bin/gh"
export PATH="$T/bin:$PATH"
cy() { (cd "$T/repo" && python3 "$S/cycle.py" "$@"); }
js() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

echo '=== the cycle a day belongs to (config: Monday titles, Saturday and Sunday plan the next Monday) ==='
for d in 2026-11-23:2026-11-23 2026-11-27:2026-11-23 2026-11-28:2026-11-30 2026-11-29:2026-11-30 2027-01-01:2026-12-28; do
  got=$(cy resolve --date "${d%%:*}" | js 'd["date"]')
  row "resolve ${d%%:*} gives the Monday ${d##*:}" "$(yes_no "$got" "${d##*:}")" ok
done
got=$(cy resolve --now 2026-11-22T22:17:00Z | js 'd["date"]')
row "the workflow's Sunday 22:17 UTC run is Monday in Asia/Tokyo" "$(yes_no "$got" 2026-11-23)" ok
got=$(cy resolve --now 2026-11-23T04:00:00Z | js 'd["date"]')
row "a run five hours late is still the same cycle" "$(yes_no "$got" 2026-11-23)" ok

echo '=== title computed once: what the workflow creates equals what the skill makes from the previous cycle ==='
# For every weekday, and for the base default and a due-date style config, the title the workflow resolves a week
# later is the title the skill builds from the previous cycle issue (cycle.py new --prev)
cat > "$T/due.json" <<'EOF'
{"repo": "example-org/sample-app", "title": "sample report {date}", "anchor_weekday": "friday", "lead_days": 6, "timezone": "Asia/Tokyo", "boundary": "Submitted"}
EOF
echo '{"repo": "example-org/sample-app"}' > "$T/default.json"
for c in "$T/repo/.claude/weekly-orchestrator.json" "$T/due.json" "$T/default.json"; do
  bad=0
  for i in 0 1 2 3 4 5 6; do
    day=$(python3 -c "import datetime as d; print(d.date(2026,11,23)+d.timedelta(days=$i))")
    later=$(python3 -c "import datetime as d; print(d.date(2026,11,23)+d.timedelta(days=$i+7))")
    cy --config "$c" new --date "$day" > "$T/prev.json"
    a=$(cy --config "$c" new --prev "$T/prev.json" | js 'd["title"]')
    b=$(cy --config "$c" new --date "$later" | js 'd["title"]')
    [ "$a" = "$b" ] || { bad=$((bad+1)); echo "    $day: skill $a / workflow $b"; }
  done
  row "$(basename "$c"): next cycle title equals the title resolved 7 days later, all weekdays" "mismatches=$bad" mismatches=0
done
wf="$D/skills/weekly-orchestrator-setup/assets/weekly-cycle-issue.yml"
n=$(grep -cE 'date -d|date \+%u|timedelta|\+%F' "$wf" "$S/create-cycle-issue.sh" | awk -F: '{s+=$2} END {print s}')
row "the workflow template and create-cycle-issue.sh do no date arithmetic" "lines=$n" lines=0
n=$(grep -c 'create-cycle-issue.sh' "$wf")
row "the workflow template runs create-cycle-issue.sh" "$( [ "$n" -ge 1 ] && echo ok || echo missing)" ok

echo '=== create-cycle-issue.sh: dedup by exact title ==='
run_create() { rm -f "$T/log"; (cd "$T/repo" && CYCLE_NOW=2026-11-22T22:17:00Z bash "$S/create-cycle-issue.sh" > "$T/out" 2>&1); echo $?; }
rc=$(run_create)
row "only a similar title exists (\"... retro\"): exit" "$rc" 0
row "only a similar title exists: issue created" "$(grep -c '^create' "$T/log" 2>/dev/null || echo 0)" 1
row "the created title is the resolved one" "$(grep -c -- '--title sample weekly 2026-11-23 --body-file' "$T/log")" 1
row "issue_fields set with the next Monday as the date" "$(grep -c 'dateValue: "2026-11-30"' "$T/log")" 1
touch "$T/viewfail"; rc=$(run_create)
row "the new issue's id cannot be read: still exit" "$rc" 0
row "the new issue's id cannot be read: issue created, fields skipped" "$(grep -c '^create' "$T/log")/$(grep -c '^fields' "$T/log")" 1/0
rm -f "$T/viewfail"
python3 - "$T/cycles.json" <<'PY'
import json, sys
p = sys.argv[1]; c = json.load(open(p))
c.append({"number": 50, "title": "sample weekly 2026-11-23", "state": "CLOSED", "closedAt": None, "body": ""})
json.dump(c, open(p, "w"))
PY
rc=$(run_create)
row "an issue with exactly the title exists (closed): exit" "$rc" 0
row "an issue with exactly the title exists (closed): nothing created" "$(grep -c '^create' "$T/log" 2>/dev/null || echo 0)" 0
cp "$FX/cycles-before.json" "$T/cycles.json"
mv "$T/cycles.json" "$T/cycles.off"   # the fake gh's issue list now fails (no file)
rc=$(run_create)
row "the issue list cannot be read: exit" "$( [ "$rc" -ne 0 ] && echo failed || echo "rc=$rc")" failed
row "the issue list cannot be read: nothing created" "$(grep -c '^create' "$T/log" 2>/dev/null || echo 0)" 0
mv "$T/cycles.off" "$T/cycles.json"

(cd "$T/repo" && python3 "$S/cycle.py" exists --title "sample weekly 2099-01-05" --limit 5 > /dev/null 2>&1); rc=$?
row "no match but the list filled --limit: an error, not \"no such issue\"" "$rc" 2
(cd "$T/repo" && python3 "$S/cycle.py" exists --title "sample weekly 2099-01-05" --limit 6 > /dev/null 2>&1); rc=$?
row "no match and the list ended before --limit: exit" "$rc" 0

echo '=== new --prev: carry-over ==='
cy new --prev "$FX/prev-closed.json" > "$T/next.json"
body() { js 'd["body"]' < "$T/next.json"; }
row "title moves to the next Monday" "$(js 'd["title"]' < "$T/next.json" | tr ' ' _)" sample_weekly_2026-11-23
row "an unchecked item is carried" "$(body | grep -c '^- \[ \] (carried over) Write the install page (#21)$')" 1
row "a carried item is not marked twice" "$(body | grep -c '(carried over) (carried over)')" 0
row "a checked item is not carried" "$(body | grep -c 'plain fields')" 0
row "a checkbox under ## Result is not carried" "$(body | grep -c 'in the result')" 0
row "the new plan section is a Draft" "$(body | grep -c '^\*\*Plan status\*\*: Draft')" 1
row "the batch table starts empty" "$(body | grep -c 'start_session')" 0
row "the PRs column of the base template is there" "$(body | grep -c '| PRs |')" 1

echo '=== new --into: splice only the plan section ==='
python3 - "$T/next.json" "$T/cur-draft.json" "$T/cur-confirmed.json" "$T/cur-other.json" "$T/cur-none.json" <<'PY'
import json, sys
new = json.load(open(sys.argv[1]))
draft = "Created by the weekly workflow.\n\n" + new["body"].replace("(carried over) Write the install page (#21)\n", "") + "\nFooter kept as is.\n"
json.dump({"title": new["title"], "body": draft}, open(sys.argv[2], "w"))
json.dump({"title": new["title"], "body": draft.replace("Draft (before the user's OK)", "Confirmed 2026-11-23")}, open(sys.argv[3], "w"))
json.dump({"title": "sample weekly 2026-11-30", "body": draft}, open(sys.argv[4], "w"))
json.dump({"title": new["title"], "body": "No markers here."}, open(sys.argv[5], "w"))
PY
cy new --prev "$FX/prev-closed.json" --into "$T/cur-draft.json" > "$T/spliced.json"; rc=$?
row "a Draft plan section is replaced: exit" "$rc" 0
row "text before the plan section is kept" "$(js 'd["body"].startswith("Created by the weekly workflow.")' < "$T/spliced.json")" True
row "text after the plan section is kept" "$(js '"Footer kept as is." in d["body"]' < "$T/spliced.json")" True
row "the carried item is now in it" "$(js '"(carried over) Write the install page" in d["body"]' < "$T/spliced.json")" True
cy new --prev "$FX/prev-closed.json" --into "$T/cur-confirmed.json" > /dev/null 2> "$T/err"; rc=$?
row "a Confirmed plan section is refused: exit" "$rc" 2
cy new --prev "$FX/prev-closed.json" --into "$T/cur-other.json" > /dev/null 2>&1; rc=$?
row "an issue with another title is refused: exit" "$rc" 2
cy new --prev "$FX/prev-closed.json" --into "$T/cur-none.json" > /dev/null 2>&1; rc=$?
row "a body without plan markers is refused: exit" "$rc" 2
python3 - "$T/cur-draft.json" "$T/cur-nostatus.json" <<'PY'
import json, re, sys
d = json.load(open(sys.argv[1])); d["body"] = re.sub(r"\*\*Plan status\*\*.*\n", "", d["body"]); json.dump(d, open(sys.argv[2], "w"))
PY
cy new --prev "$FX/prev-closed.json" --into "$T/cur-nostatus.json" > /dev/null 2>&1; rc=$?
row "a plan section without a Plan status line is refused: exit" "$rc" 2

echo '=== boundary: Tally start -> Cutoff / Submitted -> close time ==='
# ":" ends a word in run-all.sh's verdict rows, so times are compared with "." in its place
bnd() { printf '%s' "$1" > "$T/b.json"; cy boundary "$T/b.json" | js 'd["at"]+"|"+d["source"]' | tr ' :' '_.'; }
row "Tally start wins over Cutoff" "$(cy boundary "$FX/prev-closed.json" | js 'd["at"]' | tr ':' .)" 2026-11-23T08.00.00+09.00
row "Cutoff wins over close time" "$(bnd '{"body":"x\n## Result\n- **Cutoff**: 2026-11-23 09:30\n","closedAt":"2026-11-24T00:00:00Z"}')" "2026-11-23T09.30.00+09.00|##_Result_Cutoff_line"
row "Submitted is read like Cutoff" "$(bnd '{"body":"## Result\n- **Submitted**: 2026-11-27 17:30\n","closedAt":"2026-11-28T00:00:00Z"}')" "2026-11-27T17.30.00+09.00|##_Result_Submitted_line"
row "an older Japanese result reads the same" "$(bnd '{"body":"## 結果\n- **提出**: 2026-11-27 17:30\n","closedAt":"2026-11-28T00:00:00Z"}' | cut -d'|' -f1)" 2026-11-27T17.30.00+09.00
row "a Cutoff line without a time falls back to close time" "$(bnd '{"body":"## Result\n- **Cutoff**: 2026-11-23\n","closedAt":"2026-11-24T00:00:00Z"}' | cut -d'|' -f1)" 2026-11-24T00.00.00Z
row "a Cutoff line above ## Result does not count" "$(bnd '{"body":"- **Cutoff**: 2026-11-20 10:00\n## Result\nnone\n","closedAt":"2026-11-24T00:00:00Z"}' | cut -d'|' -f1)" 2026-11-24T00.00.00Z

echo '=== titles and config ==='
printf '{"title":"Orchestrator: sample-app 2026-W46","body":""}' > "$T/legacy.json"
row "a legacy title is read as its ISO week's Monday" "$(cy new --prev "$T/legacy.json" | js 'd["title"]' | tr ' ' _)" sample_weekly_2026-11-16
printf '{"title":"sample report 2026-11-26","body":""}' > "$T/offday.json"
a=$(cy --config "$T/due.json" new --prev "$T/offday.json" | js 'd["title"]' | tr ' ' _)
b=$(cy --config "$T/due.json" resolve --date 2026-12-03 | js 'd["title"]' | tr ' ' _)
row "a previous title off the anchor weekday gives the workflow's title for the next week" "$(yes_no "$a" "$b")" ok
echo '{"repo":"example-org/sample-app","title":"Plan {repo} {iso_week}"}' > "$T/repotitle.json"
printf '{"title":"Plan example-org/sample-app 2026-W47","body":""}' > "$T/rt.json"
row "a title with {repo} is read back" "$(cy --config "$T/repotitle.json" new --prev "$T/rt.json" | js 'd["title"]' | tr ' /' '_.')" Plan_example-org.sample-app_2026-W48
echo '{"repo":"example-org/sample-app","title":"Plan {date} {start}"}' > "$T/badph.json"
cy --config "$T/badph.json" resolve > /dev/null 2>&1; row "a title placeholder that cannot be read back is refused: exit" "$?" 2
printf '{"title":"sample weekly 2026-02-30","body":""}' > "$T/baddate.json"
cy new --prev "$T/baddate.json" > /dev/null 2>&1; row "a title with a date that does not exist is not a cycle issue: exit" "$?" 2
printf '{"title":"Release notes 2026-11-16","body":""}' > "$T/other.json"
cy new --prev "$T/other.json" > /dev/null 2>&1; row "a title that is not a cycle issue's is refused: exit" "$?" 2
echo '{"repo":"example-org/sample-app","timezone":"Mars/Olympus"}' > "$T/badtz.json"
cy --config "$T/badtz.json" resolve > /dev/null 2> "$T/err"; rc=$?
row "an unknown timezone stops instead of falling back: exit" "$rc" 2
echo '{"repo":"example-org/sample-app","goal_marker":"[Goal]","weekday":"monday"}' > "$T/typo.json"
cy --config "$T/typo.json" resolve > /dev/null 2>&1; row "an unknown config key is refused: exit" "$?" 2
cy --config "$T/missing.json" resolve > /dev/null 2>&1; row "a --config path that does not exist is refused: exit" "$?" 2
row "cron: Monday 07:17 Asia/Tokyo is Sunday 22:17 UTC" "$(cy cron --weekday monday --hour 7 | tr ' ' _)" "17_22_*_*_0"
row "the default title is the base skill's" "$(cy --config "$T/default.json" resolve --date 2026-11-24 | js 'd["title"]' | tr ' :' _.)" "Orchestrator._sample-app_2026-W48"
printf 'See #12 and example-org/other#3, then #13.\n### Heading\n' > "$T/refs.md"
cy refs "$T/refs.md" > /dev/null 2>&1; row "refs: a bare #N is found: exit" "$?" 1
printf 'See example-org/sample-app#12.\n' > "$T/refs.md"
cy refs "$T/refs.md" > /dev/null 2>&1; row "refs: owner/repo#N passes: exit" "$?" 0

echo '=== survey.py ==='
(cd "$T/repo" && python3 "$S/survey.py" --today 2026-11-24 > "$T/survey.txt" 2>&1); rc=$?
row "survey exits" "$rc" 0
has() { grep -cF -- "$1" "$T/survey.txt"; }
row "goal marker from config: [Goal] issues are goals" "$(has '- #10 [Goal] Ship the CSV importer (children 2/5 done, 1 open children Arch Review: Pending')" 1
row "goal marker from config: an issue with sub-issues but no marker is not a goal" "$(grep -c '^- #30 ' "$T/survey.txt")" 1
row "a child of another repo's #10 is not listed under this repo's goal #10" "$(grep -c '^  - #41 ' "$T/survey.txt")" 0
row "it is listed under no goal, with its parent's repo" "$(has '- #41 Port the importer to the CLI (no Priority, parent example-org/sample-cli#10 in another repo)')" 1
row "a grandchild is listed under its goal" "$(has '  - #13 Handle a BOM at the start of the file (no Priority, via #12)')" 1
row "the last child update is the newest, in the config's timezone" "$(has 'last child update 2026-11-21 (3 days ago)')" 1
row "warning: Arch Review Pending" "$(has '#11 is Arch Review: Pending')" 1
row "warning: a goal with more than 100 children" "$(has '#20 has 120 children; the survey read only 2')" 1
sect() { awk -v h="$1" 'index($0, h) == 1 {on=1; next} /^#/ {on=0} on' "$T/survey.txt"; }
row "a minimum-bar candidate by Target date" "$(sect '#### Start date or Target date' | grep -c '^- #12 Parse quoted fields (High, Target date: 2026-11-27, PR #60)')" 1
row "a minimum-bar candidate by Priority" "$(sect '#### Priority High' | grep -c '^- #12 ')" 1
row "a PR naming another repo's #12 is not linked to this repo's #12" "$(grep -c 'PR #60, #62\|PR #62' "$T/survey.txt")" 0
row "a PR closing another repo's #10 is not linked to this repo's #10" "$(grep '^- #10 ' "$T/survey.txt" | grep -c 'PR #62')" 0
row "a Start date after the cycle is not a candidate" "$(sect '#### Start date or Target date' | grep -c '#21')" 0
row "a Start date inside the cycle is a candidate" "$(sect '#### Start date or Target date' | grep -c '^- #40 ')" 1
row "the cycle issue itself is not listed as work" "$(grep -c '^- #50 ' "$T/survey.txt")" 0
row "carry-over comes from the previous cycle issue" "$(has '- [minimum bar not met] Write the install page (#21)')" 1
row "an unfinished batch is carried" "$(has '- [batch not done] #: 2 / Batch: Quoted fields')" 1
row "the previous cycle's boundary is read" "$(has 'at 2026-11-23T08:00:00+09:00 (from: ## Result Tally start line)')" 1
row "warning: no issue for this cycle yet" "$(has "no issue for this cycle ('sample weekly 2026-11-23')")" 1
python3 - "$T/repo/.claude/weekly-orchestrator.json" <<'PY'
import json, sys
p = sys.argv[1]; c = json.load(open(p)); c["goal_marker"] = ""; json.dump(c, open(p, "w"))
PY
(cd "$T/repo" && python3 "$S/survey.py" --today 2026-11-24 > "$T/survey.txt" 2>&1)
row "no goal marker: a top-level issue with sub-issues is a goal" "$(has '- #30 Clean up the build scripts (children 0/1 done')" 1

echo '=== set-up: scaffold.py and the version pin ==='
SC="$D/skills/weekly-orchestrator-setup/scripts/scaffold.py"
VER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$D/.claude-plugin/plugin.json")
mkdir -p "$T/new/.claude"; git -C "$T/new" init -q
cp "$FX/config.json" "$T/new/.claude/weekly-orchestrator.json"
printf '# Agents\n\nRules.\n' > "$T/new/AGENTS.md"
(cd "$T/new" && python3 "$SC" --skill-name sample-weekly --dry-run > /dev/null 2>&1)
row "--dry-run writes nothing" "$(ls "$T/new/.github" 2>/dev/null | wc -l | tr -d ' ')" 0
(cd "$T/new" && python3 "$SC" --skill-name sample-weekly > "$T/sc.txt" 2>&1); rc=$?
row "scaffold: exit" "$rc" 0
row "the project skill is placed" "$(grep -c 'Read and follow `weekly-orchestrator-base` first' "$T/new/.claude/skills/sample-weekly/SKILL.md")" 1
row "no placeholder is left in the placed files" "$(cat "$T/new/.claude/skills/sample-weekly/SKILL.md" "$T/new/.github/workflows/weekly-cycle-issue.yml" "$T/new/AGENTS.md" | grep -c '__[A-Z_]*__')" 0
row "the workflow's cron is Monday 07:17 Asia/Tokyo in UTC" "$(grep -c 'cron: "17 22 \* \* 0"' "$T/new/.github/workflows/weekly-cycle-issue.yml")" 1
row "the workflow pins this plugin version" "$(grep -c "ref: workflow--v$VER\$" "$T/new/.github/workflows/weekly-cycle-issue.yml")" 1
row "the Weekly plan section is appended once" "$(grep -c '^## Weekly plan$' "$T/new/AGENTS.md")" 1
(cd "$T/new" && python3 "$SC" --skill-name sample-weekly > /dev/null 2>&1); rc=$?
row "a second run refuses to overwrite: exit" "$( [ "$rc" -ne 0 ] && echo refused || echo "rc=$rc")" refused
row "the notes file is unchanged by the refused run" "$(grep -c '^## Weekly plan$' "$T/new/AGENTS.md")" 1
(cd "$T/new" && python3 "$S/survey.py" --today 2026-11-24 2>&1) | grep -c 'runs the scripts of workflow' > "$T/n"
row "matching pin: no skew warning" "$(cat "$T/n")" 0
sed -i.bak "s/ref: workflow--v$VER/ref: workflow--v99.0.0/" "$T/new/.github/workflows/weekly-cycle-issue.yml"
(cd "$T/new" && python3 "$S/survey.py" --today 2026-11-24 2>&1) | grep -c 'runs the scripts of workflow' > "$T/n"
row "a newer pin (a later release, same computation): no skew warning" "$(cat "$T/n")" 0
sed -i.bak "s/ref: workflow--v99.0.0/ref: workflow--v0.0.1/" "$T/new/.github/workflows/weekly-cycle-issue.yml"
(cd "$T/new" && python3 "$S/survey.py" --today 2026-11-24 2>&1) | grep -c 'runs the scripts of workflow 0.0.1' > "$T/n"
row "a pin older than the last change to the computation: the survey warns" "$(cat "$T/n")" 1
