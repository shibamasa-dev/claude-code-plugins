#!/bin/bash
# testcase-lint: one row per rule in the hook docstring, each with a passing and a violating input.
#
# Test inputs: the repo has NO real test-case file (no *.feature / *.gherkin, no `testcase: true` .md), so every
# case file here is SYNTHESIZED. The steps are built from the style guide's own wording: the "After" column of its
# Before/After table is the clean Then line, and a violating input is that same line with one vague word added.
# The Japanese cases are my translation of those lines (the repo has no Japanese test case either).
# Expected results come from the rules (hook docstring, style guide, SKILL.md), not from the hook's output.
# The forbidden words are read from a COPY of the real style-guide.md, never redefined here.
set -u
SRC="$(cd "$(dirname "$0")/.." && pwd)"
T=$(mktemp -d "${TMPDIR:-/tmp}/tcl-test.XXXX") || exit 1
trap 'rm -rf "$T"' EXIT
# a plugin-shaped copy: the hook resolves the style guide as ../skills/testcase-generator/references/style-guide.md
P="$T/plugin"; SG=skills/testcase-generator/references/style-guide.md
mkdir -p "$P/hooks" "$P/$(dirname "$SG")" "$T/f" || exit 1
cp "$SRC/hooks/testcase-lint.py" "$P/hooks/" && cp "$SRC/$SG" "$P/$SG" || exit 1
H="$P/hooks/testcase-lint.py"
fail=0
row() { printf '  %-62s -> %s (expect %s)\n' "$1" "$2" "$3"; [ "$2" = "$3" ] || fail=1; }

# verdict of one run: block (exit 2) / notrun / warn / silent; anything else (crash, odd exit) is reported as such
verdict() { # <hook> <stdin text>
  out=$(printf '%s' "$2" | python3 "$1" 2>"$T/err"); rc=$?
  if [ $rc = 2 ]; then echo block
  elif [ $rc != 0 ]; then echo "exit$rc"
  elif [ -z "$out" ]; then echo silent
  elif printf '%s' "$out" | grep -q 'NOT RUN'; then echo notrun
  elif printf '%s' "$out" | grep -q 'WARN'; then echo warn
  else echo other; fi
}
call() { verdict "$H" "{\"tool_name\":\"${2:-Write}\",\"tool_input\":{\"file_path\":\"$1\"}}"; }
mk() { printf '%s\n' "$2" > "$T/f/$1"; echo "$T/f/$1"; }   # mk <name> <content> -> path

HEAD='Feature: Order list

  @P1 @UI
  Scenario: Pending orders are listed'
CLEAN="$HEAD
    Given there are 3 orders with status \"Pending\"
    When  the tester opens the order list
    Then  The list shows 3 rows with status \"Pending\", and the count field shows \"3\""
VAGUE="$CLEAN
    And   The list shows up properly"
JA_CLEAN='機能: 注文一覧

  @P1 @UI
  シナリオ: 保留中の注文が一覧に出る
    前提 状態が「保留中」の注文が3件ある
    もし 注文一覧を開く
    ならば 一覧に状態「保留中」の行が3行表示され、件数欄は「3」になる'
JA_VAGUE="$JA_CLEAN
    ならば 一覧が正しく表示される"

echo "-- vague words: BLOCK (exit 2)"
row 'clean .feature passes silently'                      "$(call "$(mk clean.feature "$CLEAN")")" silent
row 'vague word (English) in .feature blocks'             "$(call "$(mk vague.feature "$VAGUE")")" block
row 'vague word matches in any case (Properly)'           "$(call "$(mk upper.feature "${CLEAN/Then /Then Properly }")")" block
row 'vague word is a whole word (incorrectly passes)'     "$(call "$(mk whole.feature "${CLEAN/Then /Then incorrectly }")")" silent
row 'Japanese clean case (シナリオ) passes silently'      "$(call "$(mk ja-clean.feature "$JA_CLEAN")")" silent
row 'Japanese vague word (正しく) blocks'                 "$(call "$(mk ja-vague.feature "$JA_VAGUE")")" block
# each word from the real style guide, appended to a clean case: all must block (word list is read, not redefined)
allw=all
while IFS= read -r w; do [ "$(call "$(mk w.feature "$CLEAN
    And   $w")")" = block ] || allw="miss:$w"; done < <(sed -n '/lint:vague-words -->/,/\/lint:vague-words/p' "$SRC/$SG" | sed -n 's/^- //p')
row 'every vague word listed in the style guide blocks'   "$allw" all
row 'block message names the line and the word'           "$(call "$T/f/vague.feature" >/dev/null; grep -q 'L[0-9]*: "properly"' "$T/err" && echo named || echo unnamed)" named
row '.gherkin extension is checked'                       "$(call "$(mk v.gherkin "$VAGUE")")" block
row 'Edit tool is checked too'                            "$(call "$T/f/vague.feature" Edit)" block
row '.md with frontmatter testcase: true, vague blocks'   "$(call "$(mk tc.md "---
testcase: true
---
$VAGUE")")" block
row '.md with frontmatter testcase: true, clean passes'   "$(call "$(mk tc-clean.md "---
testcase: true
---
$CLEAN")")" silent

echo "-- internal terms: WARN (exit 0, injected context)"
row 'API path in a case only warns'                       "$(call "$(mk api.feature "$CLEAN
    And   the tester sends GET /api/orders")")" warn
row 'internal constant name only warns'                   "$(call "$(mk const.feature "$CLEAN
    And   the status is ORDER_PENDING")")" warn
row 'vague + internal term: still blocks'                 "$(call "$(mk both.feature "$VAGUE
    And   the status is ORDER_PENDING")")" block
row 'block message mentions the suspected internal terms' "$(call "$T/f/both.feature" >/dev/null; grep -q 'suspected internal terms' "$T/err" && echo mentioned || echo missing)" mentioned

echo "-- out of scope: completely silent"
row 'tool other than Edit/Write (Read)'                   "$(call "$T/f/vague.feature" Read)" silent
row 'tool other than Edit/Write (Bash)'                   "$(call "$T/f/vague.feature" Bash)" silent
row '.txt file with a vague word'                         "$(call "$(mk note.txt "$VAGUE")")" silent
row '.txt with frontmatter testcase: true (only .md counts)' "$(call "$(mk fm.txt "---
testcase: true
---
$VAGUE")")" silent
row '.md without frontmatter'                             "$(call "$(mk plain.md "$VAGUE")")" silent
row '.md with testcase: true only in the body'            "$(call "$(mk body.md "# Notes
testcase: true
$VAGUE")")" silent
row '.md with testcase: false'                            "$(call "$(mk off.md "---
testcase: false
---
$VAGUE")")" silent
row '.feature without Scenario/シナリオ'                  "$(call "$(mk none.feature 'Feature: x
  The list shows up properly')")" silent
row 'file larger than 512 KiB is not read'                "$(python3 -c "print('Scenario: x properly\n' * 30000)" > "$T/f/big.feature"; call "$T/f/big.feature")" silent
row 'file does not exist'                                 "$(call "$T/f/missing.feature")" silent
row 'no file_path'                                        "$(verdict "$H" '{"tool_name":"Write","tool_input":{}}')" silent
row 'stdin is not JSON'                                   "$(verdict "$H" 'not json')" silent
row 'stdin is empty'                                      "$(verdict "$H" '')" silent
row 'style guide itself (.md, no testcase flag)'          "$(call "$SRC/$SG")" silent

echo "-- cannot run the check: say so, never block, never pass silently"
rm "$P/$SG"
row 'style guide missing: NOT RUN notice, no block'       "$(call "$T/f/vague.feature")" notrun
printf '# no markers\n' > "$P/$SG"
row 'style guide without any word blocks: NOT RUN'        "$(call "$T/f/vague.feature")" notrun
cp "$SRC/$SG" "$P/$SG"
sed 's/<!-- lint:vague-words -->//' "$SRC/$SG" | sed 's/<!-- lint:internal-term-patterns -->//' > "$P/$SG"
row 'broken markers: NOT RUN'                             "$(call "$T/f/vague.feature")" notrun
cp "$SRC/$SG" "$P/$SG"
row 'restored style guide blocks again'                   "$(call "$T/f/vague.feature")" block

exit $fail
