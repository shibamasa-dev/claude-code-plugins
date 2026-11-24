#!/usr/bin/env python3
"""Fill an Excel (.xlsx) certificate form by item label, not by cell address.

Standard library only (Python 3.9+). The form is edited in place in its XML: only the target
<c> elements of the sheet change, every other byte of the package stays as it was, so the
dropdowns and checkboxes Excel keeps in the x14 extension list survive (openpyxl drops them).

Commands
  inspect FORM [--sheet NAME] [--json]   Show the layout row by row: text cells and empty inputs
  read    FORM SPEC [--json]             Resolve each field of SPEC and print the value it holds
  fill    FORM SPEC OUT [--overwrite]    Write SPEC's values into a copy of FORM at OUT
  verify  FORM OUT SPEC [--json]         Read OUT back: values match SPEC, nothing else changed

SPEC is a JSON file: {"sheet": "<optional sheet name>", "fields": [<field>, ...]}.
A field names an item label and, optionally, a text inside that item's block:
  {"item": "事業所名", "value": "..."}                  the input right of the item label
  {"item": "証明日", "date": "2026-11-24"}               the inputs left of 年 / 月 / 日
  {"item": "雇用の形態", "check": "正社員"}               the checkbox left of the option text
  {"item": "就労実績", "left_of": "日/月", "nth": 2, "value": 20}
  {"item": "就労時間(固定就労の場合)", "below": "月", "value": true}
Optional keys: "item_nth" (which occurrence of the item label), "nth" (which occurrence of the
text inside the block), "key" (a name shown in the output). Labels match after NFKC and with all
whitespace removed; an exact match wins, otherwise a unique prefix match. Anything ambiguous or
missing is an error that lists the candidates, never a first hit.
"""
import argparse
import json
import posixpath
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CHECKBOX = {"□", "☐", "☑", "☒", "■"}
CHECKED = "☑"
UNCHECKED = "□"


class FormError(Exception):
    pass


def parse_xml(data):
    """ElementTree without DTDs: a form downloaded from a website is not trusted to be benign."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise FormError("the workbook XML declares a DTD or entities; refusing to parse it")
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise FormError("the workbook XML is broken (%s)" % e)


# ---------- addresses ----------

def col_to_num(letters):
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def num_to_col(n):
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def parse_addr(addr):
    m = re.match(r"^\$?([A-Z]+)\$?(\d+)$", addr)
    if not m:
        raise FormError("bad cell address: %s" % addr)
    return int(m.group(2)), col_to_num(m.group(1))


def addr(r, c):
    return "%s%d" % (num_to_col(c), r)


def norm(text):
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"\s+", "", t)


# ---------- reading the package ----------

def _text_of(el):
    """Text of a <si> or <is> element, without phonetic runs (<rPh>)."""
    parts = []
    for child in el:
        tag = child.tag.split("}")[-1]
        if tag == "t":
            parts.append(child.text or "")
        elif tag == "r":
            for t in child.findall("m:t", NS):
                parts.append(t.text or "")
    return "".join(parts)


class Sheet:
    def __init__(self, name, path, xml):
        self.name = name
        self.path = path
        self.xml = xml
        self.values = {}      # (r, c) -> value (str or number)
        self.formulas = set()
        self.merged = {}      # (r, c) of every merged cell -> (r1, c1, r2, c2)
        self.validated = set()
        self.max_row = 0
        self.max_col = 0

    def anchor(self, r, c):
        rng = self.merged.get((r, c))
        return (rng[0], rng[1]) if rng else (r, c)

    def bounds(self, r, c):
        return self.merged.get((r, c)) or (r, c, r, c)

    def is_anchor(self, r, c):
        return self.anchor(r, c) == (r, c)


class Workbook:
    def __init__(self, path):
        self.path = path
        try:
            self.zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, FileNotFoundError) as e:
            raise FormError("%s is not a readable .xlsx file (%s). Convert .xls with Excel or "
                            "LibreOffice first; PDF forms can't be filled by this script" % (path, e))
        self.names = self.zf.namelist()
        self.shared = self._shared_strings()
        self.sheets = self._sheet_list()

    def read(self, name):
        return self.zf.read(name)

    def _shared_strings(self):
        if "xl/sharedStrings.xml" not in self.names:
            return []
        root = parse_xml(self.read("xl/sharedStrings.xml"))
        return [_text_of(si) for si in root.findall("m:si", NS)]

    def _sheet_list(self):
        wb = parse_xml(self.read("xl/workbook.xml"))
        rels = parse_xml(self.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels.findall("{%s}Relationship" % REL_NS)}
        out = []
        for s in wb.findall("m:sheets/m:sheet", NS):
            target = targets[s.get("{%s}id" % R_NS)]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            out.append((s.get("name"), path))
        return out

    def sheet(self, name=None):
        if not self.sheets:
            raise FormError("the workbook has no sheets")
        if name is None:
            sname, path = self.sheets[0]
        else:
            hits = [s for s in self.sheets if s[0] == name] or [s for s in self.sheets if norm(s[0]) == norm(name)]
            if not hits:
                raise FormError("no sheet named %r; sheets: %s" % (name, ", ".join(s[0] for s in self.sheets)))
            sname, path = hits[0]
        xml = self.read(path).decode("utf-8")
        sh = Sheet(sname, path, xml)
        root = parse_xml(xml)
        for c in root.iter("{%s}c" % NS["m"]):
            r, col = parse_addr(c.get("r"))
            sh.max_row = max(sh.max_row, r)
            sh.max_col = max(sh.max_col, col)
            t = c.get("t")
            v = c.find("m:v", NS)
            if c.find("m:f", NS) is not None:
                sh.formulas.add((r, col))
            if t == "s" and v is not None:
                sh.values[(r, col)] = self.shared[int(v.text)]
            elif t == "inlineStr":
                is_ = c.find("m:is", NS)
                sh.values[(r, col)] = _text_of(is_) if is_ is not None else ""
            elif v is not None and v.text is not None:
                if t in ("str", "e"):
                    sh.values[(r, col)] = v.text
                elif t == "b":
                    sh.values[(r, col)] = v.text == "1"
                else:
                    num = float(v.text)
                    sh.values[(r, col)] = int(num) if num.is_integer() else num
        for mc in root.iter("{%s}mergeCell" % NS["m"]):
            a, b = mc.get("ref").split(":")
            r1, c1 = parse_addr(a)
            r2, c2 = parse_addr(b)
            for rr in range(r1, r2 + 1):
                for cc in range(c1, c2 + 1):
                    sh.merged[(rr, cc)] = (r1, c1, r2, c2)
            sh.max_row = max(sh.max_row, r2)
            sh.max_col = max(sh.max_col, c2)
        for sq in re.findall(r"<(?:xm:)?sqref>([^<]+)</(?:xm:)?sqref>", xml) + \
                re.findall(r'<dataValidation\b[^>]*\ssqref="([^"]+)"', xml):
            for part in sq.split():
                ends = part.split(":")
                r1, c1 = parse_addr(ends[0])
                r2, c2 = parse_addr(ends[-1])
                for rr in range(r1, r2 + 1):
                    for cc in range(c1, c2 + 1):
                        sh.validated.add((rr, cc))
        return sh


# ---------- locating fields ----------

def _text_cells(sh, rows=None, min_col=1):
    out = []
    for (r, c), v in sh.values.items():
        if rows is not None and not (rows[0] <= r <= rows[1]):
            continue
        if c < min_col or not sh.is_anchor(r, c):
            continue
        if isinstance(v, str) and norm(v) and norm(v) not in CHECKBOX:
            out.append((r, c))
    return sorted(out)


def _match(sh, cells, query, what):
    q = norm(query)
    exact = [rc for rc in cells if norm(sh.values[rc]) == q]
    if exact:
        return exact
    prefix = [rc for rc in cells if norm(sh.values[rc]).startswith(q)]
    if prefix:
        return prefix
    near = [norm(sh.values[rc]) for rc in cells if q[:2] and q[:2] in norm(sh.values[rc])]
    raise FormError("%s %r not found%s" % (what, query, ("; similar: " + ", ".join(sorted(set(near))[:12])) if near else ""))


def _pick(sh, hits, nth, what, query):
    if nth is None:
        if len(hits) > 1:
            raise FormError("%s %r is ambiguous (%d matches: %s); add nth" % (
                what, query, len(hits), ", ".join("%s=%s" % (addr(*rc), norm(sh.values[rc])) for rc in hits)))
        return hits[0]
    if not 1 <= nth <= len(hits):
        raise FormError("%s %r has %d matches, nth=%d is out of range" % (what, query, len(hits), nth))
    return hits[nth - 1]


def block_of(sh, item_rc):
    """Rows of an item: from the label down to the row before the next label in the same column."""
    r1, c1, r2, _ = sh.bounds(*item_rc)
    end = sh.max_row
    for (r, c) in _text_cells(sh, (r2 + 1, sh.max_row)):
        if c == c1:
            end = r - 1
            break
    return (r1, end), c1


def _is_input(sh, rc):
    v = sh.values.get(rc)
    return v not in (None, "") or rc in sh.merged or rc in sh.validated


def _step(sh, start, delta, field, strict):
    """The cell next to a text in one direction. Plain empty spacer cells (not merged, no dropdown)
    are skipped up to the first input; a text cell on the way is an error, not an input."""
    first = None
    r, c = start
    while 1 <= r <= sh.max_row and 1 <= c <= sh.max_col:
        rc = sh.anchor(r, c)
        if first is None:
            first = rc
        if _is_input(sh, rc):
            v = sh.values.get(rc)
            if strict and isinstance(v, str) and norm(v) and norm(v) not in CHECKBOX:
                raise FormError("the cell next to the text of %r holds %r at %s: a label, or a value already "
                                "filled in. Try another direction (right_of / left_of / below), or pass "
                                "--overwrite to replace a value" % (field, norm(v), addr(*rc)))
            return rc
        r1, c1, r2, c2 = sh.bounds(*rc)
        r, c = (r2 + 1 if delta[0] > 0 else r1 - 1 if delta[0] < 0 else r,
                c2 + 1 if delta[1] > 0 else c1 - 1 if delta[1] < 0 else c)
    if first is None:
        raise FormError("nothing next to the text of %r (edge of the sheet)" % (field,))
    return first


def locate(sh, field, strict=True):
    """Return the anchor (r, c) of the cell a field points at. strict: a blank form, where the
    target must not be a label (read and verify run on filled files and pass strict=False)."""
    item = field.get("item")
    if not item:
        raise FormError("field without item: %r" % field)
    item_rc = _pick(sh, _match(sh, _text_cells(sh), item, "item"), field.get("item_nth"), "item", item)
    rows, min_col = block_of(sh, item_rc)
    nth = field.get("nth")
    for how in ("right_of", "left_of", "below", "check"):
        if how in field:
            query = field[how]
            cells = _text_cells(sh, rows, min_col)
            text_rc = _pick(sh, _match(sh, cells, query, "text in item %r:" % item), nth, "text", query)
            break
    else:
        how, text_rc = "right_of", item_rc
    r1, c1, r2, c2 = sh.bounds(*text_rc)
    if how == "right_of":
        target = _step(sh, (r1, c2 + 1), (0, 1), field, strict)
    elif how == "below":
        target = _step(sh, (r2 + 1, c1), (1, 0), field, strict)
    else:
        target = _step(sh, (r1, c1 - 1), (0, -1), field, strict)
    if target == text_rc:
        raise FormError("field %r resolves to its own label at %s" % (field, addr(*target)))
    if how == "check":
        cur = sh.values.get(target)
        if not (cur is None or norm(cur) in CHECKBOX):
            raise FormError("no checkbox left of %r (found %r at %s)" % (field["check"], cur, addr(*target)))
    return target


def expand(fields):
    """Turn date and check shorthands into plain fields with a value."""
    out = []
    for f in fields:
        if "date" in f:
            m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", str(f["date"]))
            if not m:
                raise FormError("date must be YYYY-MM-DD: %r" % f)
            base = {k: v for k, v in f.items() if k not in ("date", "nth")}
            for unit, num in zip(("年", "月", "日"), m.groups()):
                g = dict(base, left_of=unit, value=int(num))
                if f.get("nth") is not None:
                    g["nth"] = f["nth"]
                g["key"] = "%s.%s" % (f.get("key", f["item"]), unit)
                out.append(g)
        elif "check" in f:
            g = dict(f)
            g.setdefault("value", True)
            out.append(g)
        else:
            out.append(dict(f))
    return out


def cell_value(field, current):
    v = field.get("value")
    if isinstance(v, bool):
        return CHECKED if v else UNCHECKED
    return v


def load_spec(path):
    try:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, ValueError) as e:
        raise FormError("cannot read spec %s: %s" % (path, e))
    if not isinstance(spec.get("fields"), list):
        raise FormError("spec needs a fields list")
    return spec


def resolve(sh, spec, strict=True):
    rows = []
    seen = {}
    for f in expand(spec["fields"]):
        rc = locate(sh, f, strict)
        key = f.get("key") or f["item"]
        if rc in seen:
            raise FormError("%s and %s both point at %s" % (seen[rc], key, addr(*rc)))
        seen[rc] = key
        rows.append((key, f, rc))
    return rows


# ---------- writing ----------

def _cell_xml(a, style, value):
    s = ' s="%s"' % style if style is not None else ""
    if value is None or value == "":
        return '<c r="%s"%s/>' % (a, s)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return '<c r="%s"%s><v>%s</v></c>' % (a, s, repr(value) if isinstance(value, float) else value)
    text = escape(str(value))
    return '<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (a, s, text)


def _cell_re(a):
    return re.compile(r'<c r="%s"(?=[\s/>])[^>]*?(?:/>|>.*?</c>)' % a, re.S)


def set_cell(xml, r, c, value):
    a = addr(r, c)
    m = _cell_re(a).search(xml)
    if m:
        style = re.search(r'\ss="(\d+)"', m.group(0)[:m.group(0).find(">") + 1])
        new = _cell_xml(a, style.group(1) if style else None, value)
        return xml[:m.start()] + new + xml[m.end():]
    row = re.search(r'<row r="%d"(?=[\s/>])[^>]*?(/>|>(.*?)</row>)' % r, xml, re.S)
    if not row:
        raise FormError("row %d does not exist in the sheet XML; fill this cell by hand" % r)
    new = _cell_xml(a, None, value)
    if row.group(1) == "/>":
        start = row.group(0)[:-2] + ">"
        return xml[:row.start()] + start + new + "</row>" + xml[row.end():]
    body_start = row.start(2)
    for cm in re.finditer(r'<c r="([A-Z]+)\d+"', row.group(2)):
        if col_to_num(cm.group(1)) > c:
            pos = body_start + cm.start()
            return xml[:pos] + new + xml[pos:]
    pos = row.end(2)
    return xml[:pos] + new + xml[pos:]


def fill(form, spec_path, out, overwrite=False):
    wb = Workbook(form)
    spec = load_spec(spec_path)
    sh = wb.sheet(spec.get("sheet"))
    rows = resolve(sh, spec, strict=not overwrite)
    xml = sh.xml
    report = []
    for key, f, (r, c) in rows:
        if (r, c) in sh.formulas:
            raise FormError("%s (%s) holds a formula; refusing to overwrite it" % (key, addr(r, c)))
        cur = sh.values.get((r, c))
        is_box = cur is not None and norm(cur) in CHECKBOX
        if cur not in (None, "") and not is_box and not overwrite:
            raise FormError("%s (%s) already holds %r; pass --overwrite to replace it" % (key, addr(r, c), cur))
        value = cell_value(f, cur)
        if isinstance(f.get("value"), bool) and not is_box and cur not in (None, ""):
            raise FormError("%s (%s) is not a checkbox" % (key, addr(r, c)))
        xml = set_cell(xml, r, c, value)
        report.append({"key": key, "cell": addr(r, c), "value": value})
    parse_xml(xml)  # still well-formed
    with zipfile.ZipFile(out, "w") as zout:
        for info in wb.zf.infolist():
            data = xml.encode("utf-8") if info.filename == sh.path else wb.read(info.filename)
            zout.writestr(info, data)
    return {"sheet": sh.name, "out": out, "written": report}


# ---------- verifying ----------

def _strip_cells(xml, addrs):
    for a in addrs:
        xml = _cell_re(a).sub("", xml)
    return xml


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return float(a) == float(b)
    return a == b


def verify(form, out, spec_path):
    src, dst = Workbook(form), Workbook(out)
    spec = load_spec(spec_path)
    sh_src = src.sheet(spec.get("sheet"))
    sh_dst = dst.sheet(spec.get("sheet"))
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    rows = resolve(sh_src, spec)
    moved = [(k, addr(*a), addr(*b)) for (k, _, a), (_, _, b) in zip(rows, resolve(sh_dst, spec, strict=False)) if a != b]
    check("labels resolve to the same cells in OUT", not moved, "; ".join("%s %s->%s" % m for m in moved))
    for key, f, rc in rows:
        want = cell_value(f, None)
        got = sh_dst.values.get(rc)
        check("value %s (%s)" % (key, addr(*rc)), _same(got, want if want != "" else None), "got %r, want %r" % (got, want))
    targets = [addr(*rc) for _, _, rc in rows]
    check("other cells of the sheet unchanged",
          _strip_cells(sh_src.xml, targets) == _strip_cells(sh_dst.xml, targets))
    others = [n for n in src.names if n != sh_src.path]
    check("same package parts", sorted(src.names) == sorted(dst.names))
    changed = [n for n in others if n in dst.names and src.read(n) != dst.read(n)]
    check("other parts byte-identical", not changed, ", ".join(changed))
    for tag in ("<x14:dataValidation ", "<dataValidation ", "<mergeCell "):
        a, b = sh_src.xml.count(tag), sh_dst.xml.count(tag)
        check("count of %s kept" % tag.strip("< "), a == b, "%d -> %d" % (a, b))
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


# ---------- inspecting ----------

def inspect(form, sheet=None):
    wb = Workbook(form)
    sh = wb.sheet(sheet)
    rows = {}
    for r in range(1, sh.max_row + 1):
        for c in range(1, sh.max_col + 1):
            if not sh.is_anchor(r, c):
                continue
            v = sh.values.get((r, c))
            merged = (r, c) in sh.merged
            if v is None or v == "":
                if not (merged or (r, c) in sh.validated):
                    continue
                kind, text = "input", ""
            elif isinstance(v, str) and norm(v) in CHECKBOX:
                kind, text = "checkbox", norm(v)
            elif (r, c) in sh.formulas:
                kind, text = "formula", v
            else:
                kind, text = ("text" if isinstance(v, str) else "value"), v
            r1, c1, r2, c2 = sh.bounds(r, c)
            span = addr(r, c) if (r1, c1) == (r2, c2) else "%s:%s" % (addr(r1, c1), addr(r2, c2))
            rows.setdefault(r, []).append({"cell": span, "kind": kind, "text": text,
                                           "dropdown": (r, c) in sh.validated})
    return {"sheet": sh.name, "sheets": [s[0] for s in wb.sheets], "rows": rows}


def print_inspect(res):
    print("sheets: %s   (showing %s)" % (", ".join(res["sheets"]), res["sheet"]))
    print("legend: [text]  _ empty input  ▼ dropdown  □/☑ checkbox  = formula")
    for r, cells in sorted(res["rows"].items()):
        parts = []
        for x in cells:
            dd = "▼" if x["dropdown"] else ""
            if x["kind"] == "input":
                parts.append("%s _%s" % (x["cell"], dd))
            elif x["kind"] == "checkbox":
                parts.append("%s %s" % (x["cell"], x["text"]))
            elif x["kind"] == "formula":
                parts.append("%s =%s" % (x["cell"], x["text"]))
            else:
                parts.append("%s[%s]%s" % (x["cell"], str(x["text"]).replace("\n", "⏎")[:40], dd))
        print("%4d  %s" % (r, "  ".join(parts)))


# ---------- CLI ----------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inspect")
    a.add_argument("form")
    a.add_argument("--sheet")
    a.add_argument("--json", action="store_true")
    a = sub.add_parser("read")
    a.add_argument("form")
    a.add_argument("spec")
    a.add_argument("--json", action="store_true")
    a = sub.add_parser("fill")
    a.add_argument("form")
    a.add_argument("spec")
    a.add_argument("out")
    a.add_argument("--overwrite", action="store_true", help="replace cells that already hold a value")
    a = sub.add_parser("verify")
    a.add_argument("form")
    a.add_argument("out")
    a.add_argument("spec")
    a.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.cmd == "inspect":
            res = inspect(args.form, args.sheet)
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=1))
            else:
                print_inspect(res)
        elif args.cmd == "read":
            wb = Workbook(args.form)
            spec = load_spec(args.spec)
            sh = wb.sheet(spec.get("sheet"))
            res = [{"key": k, "cell": addr(*rc), "value": sh.values.get(rc)} for k, _, rc in resolve(sh, spec, strict=False)]
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=1))
            else:
                for x in res:
                    print("%-6s %s = %r" % (x["cell"], x["key"], x["value"]))
        elif args.cmd == "fill":
            if args.out == args.form:
                raise FormError("OUT must differ from FORM; the form itself is never modified")
            print(json.dumps(fill(args.form, args.spec, args.out, args.overwrite), ensure_ascii=False, indent=1))
        elif args.cmd == "verify":
            res = verify(args.form, args.out, args.spec)
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=1))
            else:
                for c in res["checks"]:
                    print("%s %s %s" % ("ok  " if c["ok"] else "FAIL", c["check"], c["detail"] if not c["ok"] else ""))
                print("verify: %s" % ("ok" if res["ok"] else "FAILED"))
            return 0 if res["ok"] else 1
    except FormError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
