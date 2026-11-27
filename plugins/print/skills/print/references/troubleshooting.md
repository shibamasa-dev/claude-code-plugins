# Troubleshooting printing

Check from the top. The diagnosis commands (`lpoptions`, `lpstat`, `grep`) only read the printer's state; no paper is used. The commands that change state are marked **Changes state** below: run them only with the user's OK.

## Not duplex

1. `lpoptions -p <printer> -l | grep -iE 'duplex|sides'`: no key means the printer (or its driver) doesn't take duplex. The only way is to turn the paper over by hand
2. The key exists but it prints one-sided → check that the `-o Duplex=...` / `-o sides=...` value in the sent command matches the list's spelling (the case of `DuplexNoTumble` and so on)
3. Check that the printer's own settings don't forbid duplex and that the paper type isn't one that can't be duplexed (photo paper, postcards). Set `MediaType` to plain paper
4. A generic driver (AirPrint / IPP Everywhere) may not see the duplex unit. On macOS, enable it under System Settings → Printers & Scanners → Options & Supplies (the user does this)

## Not black and white

1. `lpoptions -p <printer> -l | grep -iE 'color|mono|gray'`: is there a black-and-white value (Gray, KGray, monochrome and so on)?
2. A key that isn't in the list (for example sending `print-color-mode` when the list has `ColorModel`) is ignored silently
3. Some printers mix color inks to make black even in "grayscale". For black ink only, look in the list for KGray or a "black only" value
4. Even when the PDF has strong color settings, ColorModel=Gray normally makes the driver print black and white. If it doesn't, suspect the driver

## A job stops or never comes out

1. `lpstat -p <printer>`: is it disabled or stopped? Read the reason line (out of paper, out of ink, offline)
2. `lpstat -o <printer>`: is the job still in the queue? A stuck job blocks the ones behind it
3. The printer's power and Wi-Fi. On macOS, look at the printer's status in System Settings
4. **Changes state:** cancel a stuck job you sent with `cancel <job ID>` (only jobs you sent; don't remove other people's)
5. **Changes state:** `cancel -a <printer>` cancels every job on the printer, other people's included. Never run it without asking the user first
6. **Changes state:** if the queue stays stopped, `cupsenable <printer>` (may need privileges; the user does this)

## No page numbers

- With `@page { margin: 0 }` in the HTML there is no room for the footer, so no number appears. Use a margin of about 10mm
- When the source PDF has no numbers and qpdf is missing, numbers can't be added (`brew install qpdf` / `apt install qpdf` fixes that). They are not added to a PDF whose pages are not all the same size either
- Whether a PDF is numbered is guessed from the top and bottom 3 lines of the first, second and last page with pdftotext. Formats other than "3", "- 3 -", "3 / 16", "3 ページ", "Page 3" and "p.3" (for example "— 3 —" or "3 頁") count as unnumbered, and numbers may be added twice. Then pass `--no-number`

## HTML breaks when turned into PDF

- Put `@page{size:A4}` and `@media print` (hide the table of contents, one column, `break-inside:avoid` on table rows and list items, wrap `pre`) into the HTML
- Diagrams drawn by JavaScript, such as Mermaid, load from a CDN and must finish within `--virtual-time-budget` (15 seconds in to_pdf.sh). An empty diagram means the time ran out or you are offline
- To check: `pdfinfo out.pdf` (page count, A4 or not) and `pdftoppm -png -r 50 -f 1 -l 3 out.pdf <scratch dir>/p` to look at a few pages as images
- On macOS, with `--user-data-dir` Chrome sometimes did not exit after writing the PDF (seen 2026-10-08). to_pdf.sh leaves it out and stops Chrome after 90 seconds
