"""Tests for certfill.py against the official forms of the Children and Families Agency.

Expected cell addresses come from the <mergeCell> list and cell layout of the two official files
(tests/fixtures/cfa-*.xlsx), read by hand, not from certfill.py's output. Filled cells are checked
with a small raw-XML reader in this file, independent of certfill.py. All values are synthetic.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
SCRIPT = os.path.join(HERE, "..", "skills", "employee-certificate", "scripts", "certfill.py")
STANDARD = os.path.join(FIX, "cfa-standard.xlsx")
SIMPLE = os.path.join(FIX, "cfa-simple.xlsx")
LAST_YEAR = os.path.join(FIX, "last-year-simple.xlsx")
SHEET = "xl/worksheets/sheet1.xml"  # the form is the first sheet in both files


def run(*args):
    p = subprocess.run([sys.executable, "-I", SCRIPT] + list(args), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def raw_cell(xlsx, ref):
    """Value of a cell straight from the package XML (no certfill code)."""
    with zipfile.ZipFile(xlsx) as z:
        sheet = z.read(SHEET).decode("utf-8")
        shared = re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8"), re.S)
    m = re.search(r'<c r="%s"(?=[\s/>])([^>]*?)(?:/>|>(.*?)</c>)' % ref, sheet, re.S)
    if not m or not m.group(2):
        return None
    attrs, body = m.group(1), m.group(2)
    if 't="inlineStr"' in attrs:
        return "".join(re.findall(r"<t[^>]*>(.*?)</t>", body, re.S))
    v = re.search(r"<v>(.*?)</v>", body).group(1)
    if 't="s"' in attrs:
        si = re.sub(r"<rPh.*?</rPh>", "", shared[int(v)], flags=re.S)
        return "".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))
    return float(v)


def write_spec(tmp, fields, sheet=None):
    path = os.path.join(tmp, "spec-%d.json" % len(os.listdir(tmp)))
    spec = {"fields": fields}
    if sheet:
        spec["sheet"] = sheet
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False)
    return path


# One spec, valid on both layouts. Values are synthetic.
FIELDS = [
    {"item": "宛", "left_of": "宛", "value": "架空市長"},
    {"item": "証明日", "date": "2026-11-24"},
    {"item": "事業所名", "value": "サンプル商事株式会社"},
    {"item": "電話番号", "value": "000"},
    {"item": "電話番号", "right_of": "―", "nth": 1, "value": "0000"},
    {"item": "電話番号", "right_of": "―", "nth": 2, "value": "0001"},
    {"item": "業種", "check": "情報通信業"},
    {"item": "本人氏名", "value": "見本 花子"},
    {"item": "本人氏名", "key": "生年月日", "date": "1990-04-01"},
    {"item": "雇用(予定)期間等", "check": "無期"},
    {"item": "雇用(予定)期間等", "date": "2020-04-01", "nth": 1},
    {"item": "雇用の形態", "check": "正社員"},
    {"item": "就労時間(固定就労の場合)", "below": "月", "value": True},
    {"item": "就労実績", "left_of": "年", "nth": 1, "value": 2026},
    {"item": "就労実績", "left_of": "月", "nth": 1, "value": 8},
    {"item": "就労実績", "left_of": "日/月", "nth": 1, "value": 20},
    {"item": "就労実績", "left_of": "時間/月", "nth": 3, "value": 160},
]

# Where each field lands, read from the mergeCell lists of the two official files.
STANDARD_CELLS = ["B2", "AA3", "AF3", "AI3", "Z4", "Z7", "AD7", "AI7", "I15", "I19",
                  "AD19", "AH19", "AJ19", "I20", "T20", "W20", "Y20", "I23", "I26",
                  "K34", "N34", "I35", "AE35"]
SIMPLE_CELLS = ["B2", "AA3", "AD3", "AG3", "Z4", "Z7", "AC7", "AG7", "I15", "I19",
                "AC19", "AF19", "AH19", "I20", "T20", "W20", "Y20", "I23", "I26",
                "K34", "N34", "I35", "AE35"]
VALUES = ["架空市長", 2026, 11, 24, "サンプル商事株式会社", "000", "0000", "0001", "☑", "見本 花子",
          1990, 4, 1, "☑", 2020, 4, 1, "☑", "☑", 2026, 8, 20, 160]


class Resolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.spec = write_spec(self.tmp, FIELDS)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cells(self, form):
        rc, out, err = run("read", form, self.spec, "--json")
        self.assertEqual(rc, 0, err)
        return [x["cell"] for x in json.loads(out)]

    def test_standard_layout(self):
        self.assertEqual(self.cells(STANDARD), STANDARD_CELLS)

    def test_simple_layout_same_labels_other_cells(self):
        self.assertEqual(self.cells(SIMPLE), SIMPLE_CELLS)

    def test_child_name_is_below_its_header(self):
        spec = write_spec(self.tmp, [{"item": "保護者記載欄", "below": "児童名", "nth": n} for n in (1, 2, 3)])
        rc, out, err = run("read", STANDARD, spec, "--json")
        self.assertEqual(rc, 0, err)
        self.assertEqual([x["cell"] for x in json.loads(out)], ["I52", "I54", "I56"])

    def test_ambiguous_item_lists_candidates(self):
        spec = write_spec(self.tmp, [{"item": "期間", "value": "x"}])
        rc, _, err = run("read", STANDARD, spec)
        self.assertEqual(rc, 2)
        self.assertIn("ambiguous", err)
        for ref in ("I37", "I39", "I41", "R43"):
            self.assertIn(ref, err)

    def test_ambiguous_text_needs_nth(self):
        spec = write_spec(self.tmp, [{"item": "保護者記載欄", "below": "児童名", "value": "x"}])
        rc, _, err = run("read", STANDARD, spec)
        self.assertEqual(rc, 2)
        self.assertIn("add nth", err)

    def test_missing_label_is_an_error(self):
        spec = write_spec(self.tmp, [{"item": "存在しない項目", "value": "x"}])
        rc, _, err = run("read", STANDARD, spec)
        self.assertEqual(rc, 2)
        self.assertIn("not found", err)

    def test_label_as_target_is_refused(self):
        # right of the second child-name header is the birth-date header, not an input
        spec = write_spec(self.tmp, [{"item": "保護者記載欄", "right_of": "児童名", "nth": 2, "value": "x"}])
        rc, _, err = run("fill", STANDARD, spec, os.path.join(self.tmp, "o.xlsx"))
        self.assertEqual(rc, 2)
        self.assertIn("O53", err)


class Fill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.spec = write_spec(self.tmp, FIELDS)
        self.out = os.path.join(self.tmp, "out.xlsx")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def fill_and_check(self, form, cells):
        rc, _, err = run("fill", form, self.spec, self.out)
        self.assertEqual(rc, 0, err)
        for ref, want in zip(cells, VALUES):
            got = raw_cell(self.out, ref)
            self.assertEqual(got, float(want) if isinstance(want, int) else want, ref)
        rc, out, err = run("verify", form, self.out, self.spec, "--json")
        self.assertEqual(rc, 0, out + err)
        self.assertTrue(json.loads(out)["ok"])

    def test_standard(self):
        self.fill_and_check(STANDARD, STANDARD_CELLS)

    def test_simple(self):
        self.fill_and_check(SIMPLE, SIMPLE_CELLS)

    def test_dropdowns_and_other_parts_survive(self):
        run("fill", STANDARD, self.spec, self.out)
        with zipfile.ZipFile(STANDARD) as a, zipfile.ZipFile(self.out) as b:
            self.assertEqual(sorted(a.namelist()), sorted(b.namelist()))
            for n in a.namelist():
                if n != SHEET:
                    self.assertEqual(a.read(n), b.read(n), n)
            sa, sb = a.read(SHEET).decode("utf-8"), b.read(SHEET).decode("utf-8")
        self.assertEqual(sa.count("<x14:dataValidation "), 15)  # counted in the official file
        self.assertEqual(sb.count("<x14:dataValidation "), 15)
        self.assertEqual(sa.count("<mergeCell "), sb.count("<mergeCell "))

    def test_form_itself_is_never_changed(self):
        before = open(STANDARD, "rb").read()
        run("fill", STANDARD, self.spec, self.out)
        self.assertEqual(open(STANDARD, "rb").read(), before)
        rc, _, err = run("fill", STANDARD, self.spec, STANDARD)
        self.assertEqual(rc, 2)

    def test_refuses_to_overwrite_a_value(self):
        run("fill", STANDARD, self.spec, self.out)
        again = os.path.join(self.tmp, "again.xlsx")
        spec = write_spec(self.tmp, [{"item": "事業所名", "value": "別の名前"}])
        rc, _, err = run("fill", self.out, spec, again)
        self.assertEqual(rc, 2)
        self.assertIn("--overwrite", err)
        rc, _, err = run("fill", self.out, spec, again, "--overwrite")
        self.assertEqual(rc, 0, err)
        self.assertEqual(raw_cell(again, "Z4"), "別の名前")

    def test_refuses_a_formula_cell(self):
        # the dropdown-list sheet computes its year column: C2 is =YEAR(TODAY()) under the header 年
        spec = write_spec(self.tmp, [{"item": "年", "below": "年", "item_nth": 1, "value": 1}], sheet="プルダウンリスト")
        rc, _, err = run("fill", STANDARD, spec, self.out)
        self.assertEqual(rc, 2)
        self.assertIn("formula", err)

    def test_unchecking_writes_the_empty_box(self):
        spec = write_spec(self.tmp, [{"item": "就労時間(固定就労の場合)", "below": "月", "value": False}])
        rc, _, err = run("fill", SIMPLE, spec, self.out)  # the simplified form ships with Mon-Fri ticked
        self.assertEqual(rc, 0, err)
        self.assertEqual(raw_cell(SIMPLE, "I26"), "☑")
        self.assertEqual(raw_cell(self.out, "I26"), "□")

    def test_cell_missing_from_its_row_is_inserted_in_order(self):
        form = os.path.join(self.tmp, "nocell.xlsx")
        with zipfile.ZipFile(STANDARD) as z, zipfile.ZipFile(form, "w") as w:
            for info in z.infolist():
                data = z.read(info.filename)
                if info.filename == SHEET:
                    data = data.decode("utf-8").replace('<c r="Z4" s="366"/>', "", 1).encode("utf-8")
                w.writestr(info, data)
        spec = write_spec(self.tmp, [{"item": "事業所名", "value": "サンプル商事株式会社"}])
        rc, _, err = run("fill", form, spec, self.out)
        self.assertEqual(rc, 0, err)
        with zipfile.ZipFile(self.out) as z:
            row = re.search(r'<row r="4".*?</row>', z.read(SHEET).decode("utf-8"), re.S).group(0)
        refs = re.findall(r'<c r="([A-Z]+4)"', row)
        self.assertEqual(refs[refs.index("Y4") + 1], "Z4")
        self.assertEqual(raw_cell(self.out, "Z4"), "サンプル商事株式会社")


class Verify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.spec = write_spec(self.tmp, FIELDS)
        self.out = os.path.join(self.tmp, "out.xlsx")
        run("fill", STANDARD, self.spec, self.out)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def tamper(self, old, new, regex=False):
        bad = os.path.join(self.tmp, "bad.xlsx")
        with zipfile.ZipFile(self.out) as z, zipfile.ZipFile(bad, "w") as w:
            for info in z.infolist():
                data = z.read(info.filename)
                if info.filename == SHEET:
                    text = data.decode("utf-8")
                    if regex:
                        text2 = re.sub(old, new, text, count=1, flags=re.S)
                        self.assertNotEqual(text2, text)
                    else:
                        self.assertIn(old, text)
                        text2 = text.replace(old, new, 1)
                    data = text2.encode("utf-8")
                w.writestr(info, data)
        rc, out, _ = run("verify", STANDARD, bad, self.spec, "--json")
        return rc, {c["check"]: c["ok"] for c in json.loads(out)["checks"]}

    def test_detects_a_change_outside_the_targets(self):
        rc, checks = self.tamper('<c r="Z5" s="366"/>',
                                 '<c r="Z5" s="366" t="inlineStr"><is><t>x</t></is></c>')
        self.assertEqual(rc, 1)
        self.assertFalse(checks["other cells of the sheet unchanged"])

    def test_detects_a_wrong_value(self):
        rc, checks = self.tamper("サンプル商事株式会社", "別会社")
        self.assertEqual(rc, 1)
        self.assertFalse(checks["value 事業所名 (Z4)"])

    def test_detects_a_lost_dropdown(self):
        # what an openpyxl round trip does to the checkbox and dropdown lists
        rc, checks = self.tamper(r"<x14:dataValidation .*?</x14:dataValidation>", "", regex=True)
        self.assertEqual(rc, 1)
        self.assertFalse(checks["count of x14:dataValidation kept"])


class CarryOver(unittest.TestCase):
    """Last year's certificate on the simplified layout, this year's on the standard one."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_values_follow_labels_across_layouts(self):
        # the birth year sits in AC19 last year (simplified form) and in AD19 this year (standard form)
        self.assertEqual(raw_cell(LAST_YEAR, "AC19"), 1990.0)
        self.assertEqual(raw_cell(LAST_YEAR, "Z4"), "サンプル商事株式会社")
        fields = [{"item": "事業所名"}, {"item": "本人氏名"}, {"item": "本人氏名", "key": "生年", "left_of": "年"},
                  {"item": "雇用の形態", "check": "正社員"}]
        rc, out, err = run("read", LAST_YEAR, write_spec(self.tmp, fields), "--json")
        self.assertEqual(rc, 0, err)
        carried = json.loads(out)
        self.assertEqual([x["cell"] for x in carried], ["Z4", "I19", "AC19", "I23"])
        self.assertEqual([x["value"] for x in carried], ["サンプル商事株式会社", "見本 花子", 1990, "☑"])
        this_year = [dict(f, value=x["value"] if x["value"] != "☑" else True) for f, x in zip(fields, carried)]
        spec = write_spec(self.tmp, this_year)
        out_path = os.path.join(self.tmp, "this-year.xlsx")
        rc, _, err = run("fill", STANDARD, spec, out_path)
        self.assertEqual(rc, 0, err)
        self.assertEqual(raw_cell(out_path, "Z4"), "サンプル商事株式会社")
        self.assertEqual(raw_cell(out_path, "I19"), "見本 花子")
        self.assertEqual(raw_cell(out_path, "AD19"), 1990.0)
        self.assertEqual(raw_cell(out_path, "I23"), "☑")


class Inspect(unittest.TestCase):
    def test_lists_sheets_and_inputs(self):
        rc, out, err = run("inspect", STANDARD)
        self.assertEqual(rc, 0, err)
        self.assertIn("標準的な様式, プルダウンリスト, 記載要領", out)
        self.assertRegex(out, r"\n\s+4\s+V4:Y4\[事業所名\]\s+Z4:AK4 _")

    def test_rejects_a_dtd(self):
        tmp = tempfile.mkdtemp()
        try:
            form = os.path.join(tmp, "dtd.xlsx")
            with zipfile.ZipFile(STANDARD) as z, zipfile.ZipFile(form, "w") as w:
                for info in z.infolist():
                    data = z.read(info.filename)
                    if info.filename == "xl/sharedStrings.xml":
                        data = data.replace(b"?>", b'?><!DOCTYPE x [<!ENTITY a "aaaa">]>', 1)
                    w.writestr(info, data)
            rc, _, err = run("inspect", form)
            self.assertEqual(rc, 2)
            self.assertIn("DTD", err)
        finally:
            shutil.rmtree(tmp)

    def test_not_an_xlsx(self):
        rc, _, err = run("inspect", os.path.join(FIX, "SOURCE.md"))
        self.assertEqual(rc, 2)
        self.assertIn(".xlsx", err)


if __name__ == "__main__":
    unittest.main(verbosity=1)
