#!/usr/bin/env python3
"""Print local files through CUPS (lp).

Defaults: black and white, duplex (long edge), A4, plain paper, 1 page per side, 1 copy.
The -o keys and values lp accepts differ per printer, so they are picked from the output of
`lpoptions -p <printer> -l`. A setting that cannot be picked is left out and reported as "Could not set".

Usage:
  print.py <file...> [--printer P] [--color] [--simplex] [--short-edge] [--size A4]
           [--copies N] [--2up] [--no-number] [--dry-run] [--lpoptions-file F]

--dry-run only prints the lp command line, page counts, sheet counts and whether pages are numbered; it sends nothing.
--lpoptions-file reads a saved `lpoptions -l` output instead of asking the printer (for tests and checking other models).
Written to run on python3.9 (the stock macOS python3).
"""
import argparse
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TO_PDF = os.path.join(HERE, "to_pdf.sh")

PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".heic"}
CONVERT_EXT = {".html", ".htm", ".md", ".markdown", ".txt", ".text", ".log", ".csv"}

MONO_RE = re.compile(r"gray|grey|mono|black", re.I)
COLOR_RE = re.compile(r"rgb|cmyk|colou?r", re.I)


def die(msg, code=1):
    print("Error: " + msg, file=sys.stderr)
    sys.exit(code)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------- Printer and accepted values ----------

def default_printer():
    """Take the default printer name from `lpstat -d`. Its language follows the OS setting (macOS answers in the
    OS language even with LANG=C), so the name is whatever follows the last colon (ASCII or full-width).
    No colon means there is no default printer."""
    if not shutil.which("lpstat"):
        die("lpstat not found (CUPS is not installed)")
    out = run(["lpstat", "-d"]).stdout.strip()
    m = re.search(r"[:：]\s*(\S+)\s*$", out)
    if not m:
        printers = run(["lpstat", "-p"]).stdout.strip()
        die("No default printer. Pass --printer.\n" + printers)
    return m.group(1)


def parse_lpoptions(text):
    """Turn `Key/Label: v1 *v2 v3` lines into {key: {"label": ..., "values": [...], "default": ...}}.
    Lines starting with # are skipped (notes in the test fixtures)."""
    opts = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([^/:\s]+)/([^:]*):\s*(.*)$", line)
        if not m:
            continue
        key, label, rest = m.groups()
        values, default = [], None
        for tok in rest.split():
            if tok.startswith("*"):
                tok = tok[1:]
                default = tok
            values.append(tok)
        opts[key] = {"label": label.strip(), "values": values, "default": default}
    return opts


def find_value(opts, key, pred):
    if key not in opts:
        return None
    for v in opts[key]["values"]:
        if pred(v):
            return v
    return None


def pick_color(opts, want_color):
    """Black and white (default) or color. Tries ColorModel, then print-color-mode, then any key whose name
    or label contains Color / Mono."""
    if want_color:
        pred = lambda v: bool(COLOR_RE.search(v)) and not MONO_RE.search(v)
        ipp = lambda v: v.lower() == "color"
    else:
        pred = lambda v: bool(MONO_RE.search(v))
        ipp = lambda v: v.lower() == "monochrome"
    v = find_value(opts, "ColorModel", pred)
    if v:
        return ("ColorModel", v)
    v = find_value(opts, "print-color-mode", ipp)
    if v:
        return ("print-color-mode", v)
    for key, o in opts.items():
        if re.search(r"colou?r|mono", key + " " + o["label"], re.I):
            v = find_value(opts, key, pred)
            if v:
                return (key, v)
    return None


def pick_duplex(opts, mode):
    """mode: long / short / simplex. Covers both Duplex (PPD) and sides (IPP)."""
    ppd = {"long": "DuplexNoTumble", "short": "DuplexTumble", "simplex": "None"}[mode]
    ipp = {"long": "two-sided-long-edge", "short": "two-sided-short-edge", "simplex": "one-sided"}[mode]
    v = find_value(opts, "Duplex", lambda x: x == ppd)
    if v:
        return ("Duplex", v)
    v = find_value(opts, "sides", lambda x: x == ipp)
    if v:
        return ("sides", v)
    return None


def pick_size(opts, size):
    s = size.lower()
    v = find_value(opts, "PageSize", lambda x: x.lower() == s)
    if v:
        return ("PageSize", v)
    # IPP media names (iso_a4_210x297mm, na_letter_8.5x11in and so on)
    v = find_value(opts, "media", lambda x: re.match(r"^[a-z]+_%s_" % re.escape(s), x.lower()) is not None)
    if v:
        return ("media", v)
    return None


def pick_plain_paper(opts):
    for key in ("MediaType", "media-type"):
        v = find_value(opts, key, lambda x: x.lower() == "stationery")
        if not v:
            v = find_value(opts, key, lambda x: x.lower().startswith("plain"))
        if v:
            return (key, v)
    return None


# ---------- Files and pages ----------

def pdf_pages(pdf):
    out = run(["pdfinfo", pdf]).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    if not m:
        die("Cannot read the page count: " + pdf)
    return int(m.group(1))


def pdf_page_sizes(pdf, n):
    out = run(["pdfinfo", "-f", "1", "-l", str(n), pdf]).stdout
    return set(re.findall(r"^Page\s+\d+\s+size:\s+([\d.]+ x [\d.]+)", out, re.M))


def has_page_numbers(pdf, n):
    """Guess with pdftotext whether page numbers are printed.
    Numbered when the top and bottom 3 lines of the first, second and last page hold "i", "- i -", "i / N",
    "i ページ" (Japanese "page i"), "Page i" or "p. i"."""
    if not shutil.which("pdftotext"):
        return None
    for i in sorted({1, min(2, n), n}):
        txt = run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", pdf, "-"]).stdout
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        edge = lines[:3] + lines[-3:]
        pats = [r"^-?\s*%d\s*-?$", r"^%d\s*/\s*\d+$", r"^%d\s*ページ", r"^(page|p\.)\s*%d\b"]
        ok = any(re.search(p % i, l, re.I) or re.search(r"(^|\s)%d\s*/\s*%d$" % (i, n), l)
                 for l in edge for p in pats)
        if not ok:
            return False
    return True


def stamp_page_numbers(pdf, n, workdir):
    """With qpdf and pages all the same size, build pages holding only a number with Chrome and overlay them.
    Returns (None, reason) when it can't."""
    if not shutil.which("qpdf"):
        return None, "qpdf not found"
    sizes = pdf_page_sizes(pdf, n)
    if len(sizes) != 1:
        return None, "pages are not all the same size"
    w, h = sizes.pop().split(" x ")
    base = os.path.splitext(os.path.basename(pdf))[0]
    html = os.path.join(workdir, base + ".numbers.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><head><meta charset='utf-8'><style>"
                "@page{size:%spt %spt;margin:0 0 12mm 0;}html,body{margin:0;}"
                "div{break-after:page;height:1px;}div:last-child{break-after:auto;}"
                "</style></head><body>%s</body></html>" % (w, h, "<div></div>" * n))
    overlay = os.path.join(workdir, base + ".numbers.pdf")
    r = run([TO_PDF, html, overlay])
    if r.returncode != 0 or pdf_pages(overlay) != n:
        return None, "could not build the number pages: " + (r.stderr.strip() or "page count differs")
    out = os.path.join(workdir, base + ".numbered.pdf")
    r = run(["qpdf", pdf, "--overlay", overlay, "--", out])
    if r.returncode not in (0, 3) or not os.path.exists(out):  # 3 means success with warnings
        return None, "qpdf could not overlay them: " + r.stderr.strip()
    return out, None


def prepare(path, args, workdir):
    """Get a file ready to print and return {src, file, kind, pages, numbers, note}."""
    if not os.path.isfile(path):
        die("File not found: " + path)
    ext = os.path.splitext(path)[1].lower()
    item = {"src": path, "file": path, "note": ""}
    if ext in IMAGE_EXT:
        item.update(kind="image", pages=1, numbers="no (image)")
        return item
    if ext in CONVERT_EXT:
        out = os.path.join(workdir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
        cmd = [TO_PDF, path, out, "--size", args.size]
        if args.no_number:
            cmd.append("--no-page-numbers")
        r = run(cmd)
        if r.returncode == 3:
            die(r.stderr.strip())
        if r.returncode != 0:
            die("Could not convert to PDF: %s\n%s" % (path, r.stderr.strip()))
        item.update(file=out, kind="converted from " + {".html": "HTML", ".htm": "HTML", ".md": "Markdown",
                                                        ".markdown": "Markdown"}.get(ext, "text"))
    elif ext in PDF_EXT:
        item["kind"] = "PDF"
    else:
        die("Unsupported format (PDF, image, HTML, Markdown, text): " + path)

    n = pdf_pages(item["file"])
    item["pages"] = n
    found = has_page_numbers(item["file"], n)
    if found is None:
        item["numbers"] = "unknown (pdftotext not found)"
    elif found:
        item["numbers"] = "yes"
    elif args.no_number:
        item["numbers"] = "no (--no-number)"
    elif n == 1:
        item["numbers"] = "no (1 page)"
    elif item["kind"] != "PDF":
        item["numbers"] = ("no (converted, but the numbers could not be confirmed; "
                           "an @page margin of 0 in the source HTML hides them)")
    else:
        out, why = stamp_page_numbers(item["file"], n, workdir)
        if out and has_page_numbers(out, n):
            item["file"] = out
            item["numbers"] = "yes (added before printing)"
        else:
            item["numbers"] = "no (the source PDF has none; %s)" % (why or "could not confirm the added numbers")
    return item


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def sheets_for(pages, per_side, duplex):
    sides = math.ceil(pages / per_side)
    return math.ceil(sides / 2) if duplex else sides


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(description="Print through CUPS (lp). Defaults: black and white, duplex long edge, "
                                             "A4, plain paper")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--printer")
    ap.add_argument("--color", action="store_true", help="print in color")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--simplex", action="store_true", help="print one-sided")
    g.add_argument("--short-edge", action="store_true", help="duplex, short-edge binding")
    ap.add_argument("--size", default="A4")
    ap.add_argument("--copies", type=int, default=1)
    ap.add_argument("--2up", dest="two_up", action="store_true", help="2 pages per side")
    ap.add_argument("--no-number", action="store_true", help="do not add page numbers")
    ap.add_argument("--dry-run", action="store_true", help="show the settings and sheet count without sending")
    ap.add_argument("--lpoptions-file", help="a saved output of lpoptions -l")
    ap.add_argument("--keep-pdf", action="store_true",
                    help="keep the converted and numbered PDFs (prints their directory; remove it when done)")
    args = ap.parse_args()
    if args.copies < 1:
        die("--copies must be 1 or more")

    for tool in ("pdfinfo",):
        if not shutil.which(tool):
            die("%s not found (install poppler: brew install poppler / apt install poppler-utils)" % tool)

    printer = args.printer or default_printer()
    if args.lpoptions_file:
        with open(args.lpoptions_file, encoding="utf-8") as f:
            opt_text = f.read()
    else:
        r = run(["lpoptions", "-p", printer, "-l"])
        if r.returncode != 0:
            die("Cannot read the options of printer %s: %s" % (printer, r.stderr.strip()))
        opt_text = r.stdout
    opts = parse_lpoptions(opt_text)

    duplex_mode = "simplex" if args.simplex else ("short" if args.short_edge else "long")
    wanted = [
        ("color" if args.color else "black and white", pick_color(opts, args.color)),
        ({"long": "duplex long edge", "short": "duplex short edge", "simplex": "one-sided"}[duplex_mode],
         pick_duplex(opts, duplex_mode)),
        (args.size, pick_size(opts, args.size)),
        ("plain paper", pick_plain_paper(opts)),
    ]
    chosen = [(name, kv) for name, kv in wanted if kv]
    missing = [name for name, kv in wanted if not kv]
    duplex_on = duplex_mode != "simplex" and wanted[1][1] is not None

    workdir = tempfile.mkdtemp(prefix="print-skill.")
    try:
        send(args, printer, chosen, missing, duplex_on, workdir)
    finally:
        if args.keep_pdf:
            print("Converted files kept in: %s (remove it when done)" % workdir)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def send(args, printer, chosen, missing, duplex_on, workdir):
    # One directory per input, so inputs with the same name (a/report.md, b/report.md) don't overwrite each other
    items = []
    for i, p in enumerate(args.files, 1):
        d = os.path.join(workdir, str(i))
        os.mkdir(d)
        items.append(prepare(p, args, d))

    per_side = 2 if args.two_up else 1
    lp = ["lp", "-d", printer]
    if args.copies > 1:
        lp += ["-n", str(args.copies)]
    for _, (k, v) in chosen:
        lp += ["-o", "%s=%s" % (k, v)]
    if args.two_up:
        lp += ["-o", "number-up=2", "-o", "number-up-layout=lrtb"]
    lp += ["-o", "fit-to-page", "--"] + [it["file"] for it in items]

    total_pages = total_sheets = 0
    print("Printer: %s" % printer)
    for i, it in enumerate(items, 1):
        sh = sheets_for(it["pages"], per_side, duplex_on) * args.copies
        total_pages += it["pages"]
        total_sheets += sh
        conv = "" if it["file"] == it["src"] else " → %s" % it["file"]
        print("[%d] %s (%s)%s" % (i, it["src"], it["kind"], conv))
        print("    Pages: %d / Page numbers: %s / Sheets: %d" % (it["pages"], it["numbers"], sh))
    nums = {it["numbers"].split(" (")[0] for it in items}
    print("Page numbers: %s" % ("yes" if nums == {"yes"} else "no" if nums == {"no"} else "some"))
    print("Layout: %d page(s) per side" % per_side)
    print("Settings: " + ", ".join("%s (%s=%s)" % (n, k, v) for n, (k, v) in chosen)
          + ", %d page(s) per side, %d cop%s" % (per_side, args.copies, "y" if args.copies == 1 else "ies"))
    print("Could not set: %s" % (", ".join(missing) if missing else "none"))
    print("Total: %s → %s (%s)" % (plural(total_pages, "page"), plural(total_sheets, "sheet"),
                                   "duplex" if duplex_on else "one-sided"))
    print("Command: " + " ".join(shlex.quote(x) for x in lp))

    if args.dry_run:
        print("(--dry-run: nothing sent)")
        return

    r = run(lp)
    if r.returncode != 0:
        die("lp failed: " + (r.stderr.strip() or r.stdout.strip()))
    print(r.stdout.strip())
    m = re.search(r"(\S+-\d+)", r.stdout)
    job = m.group(1) if m else None
    print(run(["lpstat", "-o", printer]).stdout.strip()
          or "(The job is not in the queue: it has already printed, or the queue is stopped)")
    if job:
        print("To cancel: cancel %s" % job)


if __name__ == "__main__":
    main()
