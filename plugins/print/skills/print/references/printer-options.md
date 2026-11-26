# -o keys and values differ per printer

The settings passed as `lp -o key=value` have **key names and values that differ per printer (driver)**. Don't hard-code them; pick them every time from `lpoptions -p <printer> -l`. `print.py` parses this list and picks from it.

## Reading the list

```text
ColorModel/Color Mode: Gray *RGB
Duplex/2-Sided Printing: None *DuplexNoTumble DuplexTumble
```

- Before `/` is the key (the name passed to lp); between `/` and `:` is the label (not passed)
- After `:` are the accepted values. The one with `*` is the current default
- The label may change with the OS language; the key and values don't
- On macOS, `lpstat` / `lp` messages follow the OS language even with `LANG=C`. When reading messages by machine, don't rely on their language

## Key families (in the order print.py tries them)

| Setting | PPD (with a driver) | IPP (driverless) | Notes |
|---|---|---|---|
| Black and white | `ColorModel` with Gray / KGray / Grayscale / Mono and so on | `print-color-mode=monochrome` | If neither exists, look for a key whose name or label contains Color / Mono and a value containing Gray or Mono |
| Color | `ColorModel` with RGB / CMYK / Color | `print-color-mode=color` | |
| Duplex (long edge) | `Duplex=DuplexNoTumble` | `sides=two-sided-long-edge` | Pages turn like a book, for portrait documents |
| Duplex (short edge) | `Duplex=DuplexTumble` | `sides=two-sided-short-edge` | Landscape documents, calendar-style flip |
| One-sided | `Duplex=None` | `sides=one-sided` | |
| Paper size | `PageSize=A4` | `media=iso_a4_210x297mm` | Case-insensitive |
| Plain paper | `MediaType=stationery` / `Plain` | `media-type=stationery` | |
| 2 pages per side | `number-up=2`, `number-up-layout=lrtb` | same | Common to CUPS. Not in the list, but accepted |
| Fit to page | `fit-to-page` | same | Common to CUPS |
| Copies | `lp -n N` | same | |

Measured (2026-10-08): an EPSON EP-30VA (macOS, EPSON driver) lists `ColorModel: Gray *RGB`, `Duplex: None *DuplexNoTumble DuplexTumble`, `A4` under `PageSize` and `stationery` under `MediaType`.

The IPP and KGray rows above are inferred from the usual CUPS output format and not yet checked on a real printer. After checking a new printer, save its `lpoptions -l` output unedited in the plugin's `tests/fixtures/` (without the queue name) and add a case to `tests/cases.json`.

## Passing a setting that isn't in the list

CUPS usually ignores an `-o` that isn't in the list without an error. "I asked for black and white and got color" is usually a key or value spelled differently from the list. That is why print.py leaves out values that aren't in the list and reports them under "Could not set".
