import tempfile
from contextlib import closing
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from src.import_catalogue import import_catalogue

HEADERS = "esdscom_structure_id structurecode esdscom_path_full region structure_info esdscom_phrase_id grammar original_code english german revision_date phrase_owner source info qualifier value unit".split()

def cell(letter, row, value):
    return '<c r="' + letter + str(row) + '" t="inlineStr"><is><t>' + escape(value) + '</t></is></c>'

def small_workbook(code, english):
    letters = "ABCDEFGHIJKLMNOPQ"
    header = "".join(cell(col, 1, name) for col, name in zip(letters, HEADERS))
    row = cell("B", 2, code) + cell("I", 2, english) + cell("D", 2, "EU")
    sheet = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData><row r="1">' + header + '</row><row r="2">' + row + '</row></sheetData></worksheet>')
    import io
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return data.getvalue()

class CatalogueImportTests(unittest.TestCase):
    def test_import_original_xlsx_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "original.zip"
            target = root / "data" / "catalogue.sqlite"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("eSDScom_5_5_Core_20231131.xlsx", small_workbook("01.07.02.02.13000.", "Keep container tightly closed."))
                archive.writestr("eSDScom_5_5_ExpoScenario_20231131.xlsx", small_workbook("09.01.1000.", "Original exposure text"))
            report = import_catalogue(source, target)
            self.assertEqual(report["total_rows"], 2)
            self.assertEqual(report["english_entries"], 2)
            import sqlite3
            with closing(sqlite3.connect(target)) as conn:
                result = conn.execute("SELECT entry_key, english, sds_section, jurisdiction_structure FROM entries WHERE collection='Core'").fetchone()
                self.assertEqual(result, ("esdscom55-Core-r000002", "Keep container tightly closed.", 7, "EU"))
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0], 2)

    def test_reject_missing_workbook(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "bad.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("eSDScom_5_5_Core_20231131.xlsx", small_workbook("01.07.02.02.13000.", "Test"))
            with self.assertRaises(ValueError):
                import_catalogue(source, root / "data.sqlite")
            self.assertFalse((root / "data.sqlite").exists())

if __name__ == "__main__":
    unittest.main()
