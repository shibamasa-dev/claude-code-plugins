---
name: print
description: Print local files (PDF, image, text, HTML, Markdown) through CUPS (lp) on macOS or Linux. Defaults to black and white, duplex (long edge), A4, plain paper, 1 page per side, with page numbers; on request color, one-sided, short-edge binding, another paper size, several copies or 2 pages per side (2-up). The lp keys and values differ per printer, so they are picked from lpoptions -l by a script, and before sending it shows what, how many pages, how many sheets, which settings and which printer. Use it for "print this", "print it double-sided", "print in black and white", "2 pages per sheet", or in Japanese 「印刷して」「プリントして」「紙で出して」「A4 で印刷」「両面で」「白黒で刷って」「2 ページずつ割り付けて」.
last_reviewed: 2026-11-26
review_after: 2027-05-26
---

# print — print through CUPS (lp)

## Rules

1. **Never print unasked.** Printing uses paper and ink and can't be undone. Send only when the user has explicitly asked to print.
2. **Before sending, say in 1–2 lines** what, how many pages, how many sheets, which settings and which printer. If the user explicitly asked to print, send right away (don't stop to wait for a confirmation). If the request is vague ("I might want this on paper"), show it and wait for an answer.
3. **Don't hard-code keys or values.** Pick them from `lpoptions -p <printer> -l` (`scripts/print.py` does it). A value that isn't in the list is left out and reported under "Could not set".
4. **Don't write a printer name or model into the skill.** The default printer comes from `lpstat -d`.
5. **Don't cancel other people's jobs.** `cancel` only the job IDs you sent.

## Steps

### 1. Decide the file

Use the file the user points at. For HTML or other files made in the conversation, use their path. How each format is handled (`print.py` does it):

| Format | Handling |
|---|---|
| PDF | As is. If it has no page numbers, they are added before printing (below) |
| HTML | `scripts/to_pdf.sh` turns it into PDF with headless Chrome and puts "3 / 16" at the bottom center |
| Markdown | Through HTML with pandoc if present; otherwise Chrome renders it with marked (from a CDN), then PDF. Offline, it stays preformatted text |
| Text (.txt and so on) | Turned into a PDF of wrapped preformatted text |
| Image | Sent as one page (no page number) |

Without Chrome, HTML, Markdown and text can't be converted: stop and report it.

When you write the HTML yourself, keep it from breaking: add `@page{size:A4}` and `@media print` (hide the table of contents, one column, `break-inside:avoid` on table rows and list items, wrap `pre`). An `@page` margin of 0 leaves no room for page numbers.

**Page numbers**: anything converted always gets them. For a PDF, pdftotext guesses whether it already has numbers, and if not, qpdf overlays pages holding only a number. **Without qpdf, or when the pages are not all the same size, numbers can't be added, so a PDF without numbers prints without them** (the output says why). Pass `--no-number` when numbers aren't wanted.

### 2. Dry run for pages, sheets and settings

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/print/scripts/print.py" <file...> --dry-run [options]
```

| Option | Meaning (default) |
|---|---|
| `--printer P` | Printer (default: the default printer from `lpstat -d`) |
| `--color` | Color (default: black and white) |
| `--simplex` / `--short-edge` | One-sided / duplex short-edge binding (default: duplex long edge) |
| `--size A4` | Paper size (default: A4) |
| `--copies N` | Copies (default: 1) |
| `--2up` | 2 pages per side (`number-up=2`, `number-up-layout=lrtb`) |
| `--no-number` | Don't add page numbers |
| `--dry-run` | Show only, don't send |
| `--keep-pdf` | Keep the converted and numbered PDFs and print their directory (default: removed when the script ends) |

What the user asked for wins over the defaults (black and white, duplex long edge, A4, plain paper, 1 page per side). Sheets are "ceil(ceil(pages ÷ pages per side) ÷ (2 if duplex)) × copies", added up per file. On a printer where duplex could not be set, sheets are counted one-sided.

Sample output (dry run against the saved options of a real EPSON inkjet; `EVAL_PRINTER` stands in for the queue name):

```text
Printer: EVAL_PRINTER
[1] report.pdf (PDF)
    Pages: 7 / Page numbers: yes / Sheets: 4
Page numbers: yes
Layout: 1 page(s) per side
Settings: black and white (ColorModel=Gray), duplex long edge (Duplex=DuplexNoTumble), A4 (PageSize=A4), plain paper (MediaType=stationery), 1 page(s) per side, 1 copy
Could not set: none
Total: 7 pages → 4 sheets (duplex)
Command: lp -d EVAL_PRINTER -o ColorModel=Gray -o Duplex=DuplexNoTumble -o PageSize=A4 -o MediaType=stationery -o fit-to-page -- report.pdf
(--dry-run: nothing sent)
```

The path of a converted PDF is shown too, but the file is removed when the script ends. When the layout matters, run the dry run with `--keep-pdf`, render a few pages with `pdftoppm -png -r 50 -f 1 -l 3 <pdf> <prefix>`, look at them, then remove the directory printed on the last line.

### 3. Check what could not be set

If "Could not set" is anything but "none", those settings stay at the printer's default. Always include them when you tell the user (for example "this printer doesn't take duplex, so 7 sheets one-sided"). To find the cause, see [references/printer-options.md](references/printer-options.md).

### 4. Tell the user

In 1–2 lines. For example: "Sending report.pdf (7 pages, numbered) to <printer> in black and white, duplex long edge, A4, plain paper: 4 sheets."

### 5. Send and check

Run the same arguments without `--dry-run`. It prints `lp`'s request ID and the queue from `lpstat -o <printer>`; report them with the cancel command (`cancel <job ID>`).

## Troubleshooting

Not duplex, not black and white, a stuck job, no page numbers, HTML breaking in the PDF → [references/troubleshooting.md](references/troubleshooting.md)

## Dependencies

- CUPS (`lp`, `lpstat`, `lpoptions`)
- poppler (`pdfinfo`, `pdftotext`): page count and whether pages are numbered
- Google Chrome / Chromium: HTML, Markdown and text to PDF (set the path with the `CHROME` environment variable)
- Optional: qpdf (adds page numbers to an existing PDF), pandoc (Markdown conversion)
- python3 (3.9 or later, standard library only)

## Tests

The plugin's `tests/run-all.sh` grades `--dry-run` output against saved `lpoptions -l` outputs in `tests/fixtures/` (one real EPSON output and two made-up ones that use other key families), with `lp` and friends shimmed out, so no paper is used. After checking a new printer, save its `lpoptions -l` output there (with the queue name left out) and add a case to `tests/cases.json`.
