# print

English | [日本語](README.ja.md)

A skill that prints local files (PDF, image, text, HTML, Markdown) through CUPS `lp` on macOS or Linux. By default it prints in black and white, duplex long edge, on A4 plain paper, 1 page per side, with page numbers, and it tells you the pages, sheets, settings and printer before sending.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install print@shibamasa-plugins
```

## Skills

| Skill | Use it for |
|---|---|
| `print` | "Print this", "print it double-sided", "print in color", "2 pages per sheet". Claude prints only when you ask. It runs a dry run first, tells you in one or two lines what goes to which printer and how many sheets, then sends. The scripts are `skills/print/scripts/print.py` (Python, standard library only) and `skills/print/scripts/to_pdf.sh` |

## How print works

1. **Prepare the file.** A PDF is sent as is; an image as one page. HTML, Markdown and text become a PDF through headless Chrome, with "page / pages" at the bottom center (Markdown goes through pandoc when it is installed, otherwise through marked loaded from a CDN). A PDF without page numbers gets them overlaid with qpdf before printing; without qpdf, or when its pages differ in size, it prints without numbers and says why.
2. **Pick the options.** The `-o` keys and values `lp` accepts differ per printer and driver, so `print.py` reads the printer's own `lpoptions -p <printer> -l` and picks from it: PPD keys (`ColorModel`, `Duplex`, `PageSize`, `MediaType`) or IPP keys (`print-color-mode`, `sides`, `media`, `media-type`). A setting the printer doesn't list is not sent and is reported under "Could not set", because CUPS silently ignores unknown options.
3. **Count and show.** It counts pages with `pdfinfo` and sheets as `ceil(ceil(pages / pages per side) / 2 if duplex) × copies`, and prints the settings and the exact `lp` command. `--dry-run` stops here.
4. **Send.** It runs `lp`, shows the job ID and the queue (`lpstat -o`), and the `cancel <job ID>` command to take it back.

Options: `--printer`, `--color`, `--simplex`, `--short-edge`, `--size`, `--copies`, `--2up`, `--no-number`, `--dry-run`.

## Configuration

No settings. The printer is the system default from `lpstat -d` unless you name one; the plugin stores no printer name. Set `CHROME` to the browser's path if Chrome or Chromium is not in a standard place.

### Where files go

Converted and numbered PDFs go to a new directory under the system temp directory (`print-skill.*`), which is not removed after the run. Nothing is kept in plugin data; uninstalling removes nothing else.

## Limitations

- Only the IPP key family and the `KGray` value are checked against made-up `lpoptions` outputs; the only real printer checked is an EPSON inkjet with its macOS driver.
- Whether a PDF already has page numbers is a guess from the text at the top and bottom of the first, second and last page. Unusual formats (for example "— 3 —") count as unnumbered and may get a second number; pass `--no-number` then.
- Markdown without pandoc needs network access for marked; offline it prints as preformatted text.

## Requirements

- macOS or Linux with CUPS (`lp`, `lpstat`, `lpoptions`)
- poppler (`pdfinfo`, `pdftotext`): `brew install poppler` / `apt install poppler-utils`
- Google Chrome or Chromium, for HTML, Markdown and text
- Optional: qpdf (page numbers on an existing PDF), pandoc (Markdown)
- Python 3.9 or later (standard library only)

## Tests

```bash
bash plugins/print/tests/run-all.sh
```

Offline and paperless: every case runs `print.py --dry-run` against saved `lpoptions -l` outputs, and `lp`, `lpstat`, `lpoptions` and `cancel` are replaced on `PATH` by shims that record any call; the last row checks there were none. The cases that need qpdf or Chrome are skipped (and not counted) when those are missing.
