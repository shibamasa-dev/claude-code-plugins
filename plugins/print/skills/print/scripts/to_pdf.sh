#!/usr/bin/env bash
# Turns HTML / Markdown / text into a PDF with headless Chrome.
# Page numbers ("3 / 16") go at the bottom center through a CSS @page margin box.
# Chrome's own header and footer (file name, date) are removed with --no-pdf-header-footer.
#
# Usage: to_pdf.sh <input .html|.htm|.md|.markdown|.txt> <output.pdf> [--size A4] [--no-page-numbers]
# Exit codes: 0 success / 2 bad arguments / 3 no Chrome / 4 conversion failed
set -euo pipefail

usage() { echo "Usage: $0 <input> <output.pdf> [--size A4] [--no-page-numbers]" >&2; exit 2; }
[ $# -ge 2 ] || usage
IN="$1"; OUT="$2"; shift 2
SIZE=""; NUMBERS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --size) SIZE="${2:-}"; [ -n "$SIZE" ] || usage; shift 2 ;;
    --no-page-numbers) NUMBERS=0; shift ;;
    *) usage ;;
  esac
done
[ -f "$IN" ] || { echo "Input file not found: $IN" >&2; exit 2; }

find_chrome() {
  if [ -n "${CHROME:-}" ] && [ -x "$CHROME" ]; then echo "$CHROME"; return; fi
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium"; do
    [ -x "$c" ] && { echo "$c"; return; }
  done
  for c in google-chrome google-chrome-stable chromium chromium-browser; do
    command -v "$c" >/dev/null 2>&1 && { command -v "$c"; return; }
  done
  return 1
}
CHROME_BIN="$(find_chrome)" || { echo "Chrome / Chromium not found, so HTML, Markdown and text cannot be turned into PDF. Stopping (set the CHROME environment variable to its path)" >&2; exit 3; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/print-to-pdf.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
SRC_HTML="$WORK/page.html"

# Turn the input into HTML and inject the @page rule for page numbers (and the paper size when --size is given).
# HTML gets its own directory as <base>, so images and CSS on relative paths resolve.
python3 - "$IN" "$SRC_HTML" "$SIZE" "$NUMBERS" <<'PY'
import html, os, pathlib, re, shutil, subprocess, sys

src, dst, size, numbers = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1"
ext = os.path.splitext(src)[1].lower()
with open(src, encoding="utf-8", errors="replace") as f:
    text = f.read()

page_rules = []
if size:
    page_rules.append("size:%s;" % size)
if numbers:
    page_rules.append('@bottom-center{content:counter(page) " / " counter(pages);'
                      "font:9pt sans-serif;color:#444;}")
inject = "<style>@page{%s}</style>" % "".join(page_rules) if page_rules else ""
base = '<base href="%s/">' % pathlib.Path(os.path.dirname(os.path.abspath(src))).as_uri()

BODY_CSS = ("<style>body{font-family:sans-serif;line-height:1.6;}"
            "pre{white-space:pre-wrap;word-break:break-word;}"
            "table{border-collapse:collapse;}td,th{border:1px solid #999;padding:2px 6px;}"
            "tr,li,pre,img{break-inside:avoid;}</style>")

if ext in (".html", ".htm"):
    head = base + inject
    # Put it first in <head>, so the document's own @page rules (margins, size) come later and win
    m = re.search(r"<head[^>]*>", text, re.I)
    if m:
        text = text[:m.end()] + head + text[m.end():]
    else:
        text = head + text
    out = text
elif ext in (".md", ".markdown"):
    title = html.escape(os.path.basename(src))
    pandoc = shutil.which("pandoc")
    body = None
    if pandoc:
        r = subprocess.run([pandoc, "-f", "gfm", "-t", "html", src],
                           capture_output=True, text=True)
        if r.returncode == 0:
            body = r.stdout
    if body is None:
        # Without pandoc, let marked (from a CDN) render it inside Chrome. If that can't load, it stays preformatted text
        body = ('<pre id="md-src">%s</pre>'
                '<script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js" '
                'integrity="sha384-/TQbtLCAerC3jgaim+N78RZSDYV7ryeoBCVqTuzRrFec2akfBkHS7ACQ3PQhvMVi" '
                'crossorigin="anonymous"></script>'
                '<script>if(window.marked){var s=document.getElementById("md-src");'
                'var d=document.createElement("div");d.innerHTML=marked.parse(s.textContent);'
                's.replaceWith(d);}</script>') % html.escape(text)
    out = ("<!doctype html><html><head><meta charset='utf-8'><title>%s</title>%s%s%s</head>"
           "<body>%s</body></html>") % (title, base, BODY_CSS, inject, body)
else:
    out = ("<!doctype html><html><head><meta charset='utf-8'>%s%s</head>"
           "<body><pre>%s</pre></body></html>") % (BODY_CSS, inject, html.escape(text))

with open(dst, "w", encoding="utf-8") as f:
    f.write(out)
PY

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
# No --user-data-dir: with it, Chrome on macOS sometimes did not exit after writing the PDF (seen 2026-10-08).
# Stop it after 90 seconds anyway (macOS has no timeout command)
"$CHROME_BIN" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=15000 \
  --print-to-pdf="$OUT" "file://$SRC_HTML" >/dev/null 2>&1 &
CPID=$!
for _ in $(seq 1 180); do kill -0 "$CPID" 2>/dev/null || break; sleep 0.5; done
kill "$CPID" 2>/dev/null || true
wait "$CPID" 2>/dev/null || true
[ -s "$OUT" ] || { echo "Could not convert to PDF: $IN" >&2; exit 4; }
echo "$OUT"
