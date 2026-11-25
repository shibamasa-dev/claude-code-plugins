# certfill.py: commands and the spec format

## Commands

| Command | What it does |
|---|---|
| `inspect FORM [--sheet NAME] [--json]` | Prints the sheet row by row: text cells as `A1[text]`, empty inputs as `A1:C1 _`, dropdowns `▼`, checkboxes `□`/`☑`, formulas `=`. Lists every sheet; the first one is shown unless `--sheet` names another (read an instructions sheet such as `記載要領` this way) |
| `read FORM SPEC [--json]` | Resolves every field and prints `cell key = value`. On a blank form, use it to check the mapping; on last year's copy, to collect values to carry over |
| `fill FORM SPEC OUT [--overwrite]` | Writes the values into a copy at OUT (built next to it and moved into place when complete). Refuses: a field without `value`, a cell that already holds a value (without `--overwrite`), a formula cell, a target that is a label (even with `--overwrite`), two fields on one cell, OUT that is FORM under any name. Its output lists each cell written and, under `was`, any value it replaced |
| `verify FORM OUT SPEC [--json]` | Resolves the spec on FORM (where `fill` resolved it), then reads OUT back and checks each value against the spec, that no other cell (labels included) or file in the package changed, that no cell address appears twice, and that the counts of dropdowns and merged cells are the same. Exit 0 only when every check is `ok` |

Exit codes: 0 ok, 1 a verify check failed, 2 an error (the message says what to change).

## Spec

```json
{
  "sheet": "標準的な様式",
  "fields": [
    {"item": "事業所名", "value": "..."},
    {"item": "証明日", "date": "2026-04-01"},
    {"item": "雇用の形態", "check": "正社員"}
  ]
}
```

`sheet` is optional (default: the first sheet). Sheet names also match after normalization, so `"標準的な様式"` finds a sheet whose name ends in a full-width space. Each field has an `item` and at most one locator.

| Key | Meaning |
|---|---|
| `item` | The item's label as printed, for example `"事業所名"` or `"就労実績"`. Labels match after NFKC normalization with every space and line break removed, so `"就労時間(固定就労の場合)"` matches the two-line cell. An exact match wins; otherwise a unique prefix match |
| `item_nth` | Which occurrence of the label, counted top to bottom, left to right, when it repeats on the sheet |
| *(no locator)* | The input right of the item label |
| `right_of` / `left_of` / `below` | A text inside the item's block; the field is the input next to it in that direction. Units sit right of their input, so a year is `left_of: "年"`; column headers sit above, so a child's name is `below: "児童名"` |
| `check` | An option text; the field is the checkbox left of it, set to `☑` |
| `nth` | Which occurrence of the text inside the block |
| `value` | A string, a number, or `true` / `false` for a checkbox (`☑` / `□`) |
| `date` | `"YYYY-MM-DD"`: shorthand for three fields, the inputs left of `年`, `月` and `日` (with `nth` when the item has a start and an end date). Years are written in the Western calendar, as the standard form asks |
| `key` | A name shown in the output, useful when one item has several fields |

**The item's block** runs from the label's row down to the row before the next label in the same column, and from the label's column to the right edge. Texts are searched only inside it, so `年` under one item never matches the `年` of another below it. There is no boundary to the right: when two items sit side by side (a start and an end date in one row), the right one's texts are in the left one's block too, so pick with `nth`.

**Next to a text** means the nearest input in that direction. Plain empty spacer cells (not merged, no dropdown) are skipped; when a plain text cell comes first, the first empty cell was a single-cell input. Text in a plain cell always counts as a label: `fill` never writes over it, even with `--overwrite`. Only boxes (merged cells and dropdowns) take a replaced value.

Write numbers as numbers (`2026`, `20`, `160.5`): the year, month, day and hour cells of the standard form are numeric dropdowns.

## Errors and what to do

| Message | Fix |
|---|---|
| `item 'X' is ambiguous (n matches: ...)` | Add `item_nth`, or use the item's own block (for example the person's birth date as `{"item": "本人氏名", "date": ...}`, since `生年月日` also heads each child's column) |
| `text 'X' is ambiguous` | Add `nth` (counted top to bottom, then left to right inside the block) |
| `item 'X' not found; similar: ...` | Copy the label as `inspect` prints it |
| `the cell next to ... is the label ...` | Use another direction; a column header usually needs `below`. A value printed in a plain cell can't be replaced; leave it or fill by hand |
| `field ... has no value` | Add `value`; `"value": ""` clears a cell on purpose |
| `... already holds ...` | The form came prefilled, or the field points at the wrong cell. Check with `read`; use `--overwrite` only to replace a prefilled value on purpose |
| `no checkbox left of ...` | The option has no `□` cell in front of it; read the row with `inspect` |
| `... holds a formula` | The form computes that cell; fill its inputs instead |

## Example: the standard form

Field patterns that resolve on the standard layout (values are placeholders):

```json
{"fields": [
  {"item": "宛", "left_of": "宛", "value": "<municipality> 長"},
  {"item": "証明日", "date": "2026-04-01"},
  {"item": "事業所名", "value": "<company>"},
  {"item": "電話番号", "value": "<area code>"},
  {"item": "電話番号", "right_of": "―", "nth": 1, "value": "<exchange>"},
  {"item": "電話番号", "right_of": "―", "nth": 2, "value": "<number>"},
  {"item": "業種", "check": "情報通信業"},
  {"item": "本人氏名", "value": "<name>"},
  {"item": "本人氏名", "key": "生年月日", "date": "1990-01-31"},
  {"item": "雇用(予定)期間等", "check": "無期"},
  {"item": "雇用(予定)期間等", "date": "2020-04-01", "nth": 1},
  {"item": "雇用の形態", "check": "正社員"},
  {"item": "就労時間(固定就労の場合)", "below": "月", "value": true},
  {"item": "就労実績", "left_of": "年", "nth": 1, "value": 2026},
  {"item": "就労実績", "left_of": "月", "nth": 1, "value": 1},
  {"item": "就労実績", "left_of": "日/月", "nth": 1, "value": 20},
  {"item": "就労実績", "left_of": "時間/月", "nth": 1, "value": 160},
  {"item": "保護者記載欄", "below": "児童名", "nth": 1, "value": "<child>"}
]}
```

The three months of the work record are `nth` 1, 2 and 3 of `年`, `月`, `日/月` and `時間/月`, left to right; the standard instructions put the newest month at `nth` 1.
