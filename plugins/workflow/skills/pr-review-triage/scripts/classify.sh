#!/bin/bash
# Core logic that sorts a PR diff into light / heavy (calls neither gh nor git; same input gives the same output).
# Usage: classify.sh [<numstat file>]   (reads stdin when omitted)
#   Input: lines in `git diff --numstat` format, <added>\t<deleted>\t<path> (for a PR, run `git diff --numstat origin/<base>...HEAD` locally)
#   Output: line 1 is light or heavy; following lines are reasons starting with "- "
# The criteria and the reasoning behind the threshold are in SKILL.md. When in doubt, lean heavy (a miss costs more than one bot run)
set -u
MAX_LINES=200

awk -F'\t' -v max="$MAX_LINES" '
function base(p,  n, a) { n = split(p, a, "/"); return a[n] }
function list(arr, n,  s, i) {
  s = arr[1]; for (i = 2; i <= n && i <= 5; i++) s = s ", " arr[i]
  if (n > 5) s = s ", and " (n - 5) " more"
  return s
}
NF >= 3 {
  path = $3
  # Read git rename notation (dir/{a => b}.md, a => b) by the new name
  if (path ~ / => /) { gsub(/[{][^}]* => /, "", path); gsub(/[}]/, "", path); sub(/.* => /, "", path) }
  files++
  if ($1 == "-" || $2 == "-") bin[++nbin] = path   # binaries have no line counts
  else total += $1 + $2
  b = tolower(base(path))
  if (b !~ /\.(md|markdown|txt|rst|adoc)$/) nondoc[++nnon] = path
  else if (b == "skill.md" || b == "claude.md" || b == "agents.md") named[++nnam] = path
  else if (("/" path) ~ /\/(skills|hooks|agents|commands|rules|\.github)\//) behav[++nbeh] = path
}
END {
  r = ""
  if (files == 0) r = r "- Empty diff (fetching it may have failed)\n"
  if (nnon) r = r "- Non-document files: " list(nondoc, nnon) "\n"
  if (nbin) r = r "- Binary: " list(bin, nbin) "\n"
  if (nnam) r = r "- Behavior-defining documents (by file name): " list(named, nnam) "\n"
  if (nbeh) r = r "- Documents under behavior-defining paths: " list(behav, nbeh) "\n"
  if (total > max) r = r "- Changed lines: " total " > " max "\n"
  if (r != "") printf "heavy\n%s", r
  else printf "light\n- Documents only: %d files, %d lines\n", files, total
}
' "${1:-/dev/stdin}"
