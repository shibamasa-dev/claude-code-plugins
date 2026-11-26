# Changelog

Changes to the print plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.0] - 2026-11-26

### Added
- First release: the `print` skill, with its messages and skill body in English. It prints PDF, images, text, HTML and Markdown through CUPS `lp`, by default in black and white, duplex long edge, A4, plain paper, 1 page per side, with page numbers
- `scripts/print.py` picks the `-o` keys and values from the printer's own `lpoptions -l` (PPD keys such as `ColorModel` / `Duplex` and IPP keys such as `print-color-mode` / `sides`), leaves out what the printer doesn't accept and reports it under "Could not set". `--dry-run` shows pages, sheets, settings and the `lp` command without sending
- `scripts/to_pdf.sh` turns HTML, Markdown and text into PDF with headless Chrome and puts "page / pages" at the bottom center. A PDF without page numbers gets them overlaid with qpdf before printing
- No printer name is stored: the default printer comes from `lpstat -d`
