"""Standalone synthetic intake and missing-optional-dependency regression tests."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sds_intake import blocks, extract


class IntakeSmoke(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.text = "SECTION 1 Identification\nProduct: Synthetic sample\nSECTION 2 Hazards\nH315 GHS07"

    def check(self, path, ocr=False):
        document = extract(path, ocr=ocr)
        self.assertEqual(document["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIn("Synthetic sample", document["pages"][0]["text"])
        self.assertIn("1", blocks(document["pages"], {"1", "2"}))
        self.assertIn("H315", document["pages"][0]["hazard_codes"])
        return document

    def test_txt(self):
        path = self.root/"test.txt"
        path.write_text(self.text, encoding="utf-8")
        self.check(path)

    def test_json(self):
        path = self.root/"test.json"
        path.write_text(json.dumps({"pages":[{"page":1,"text":self.text}]}),encoding="utf-8")
        self.check(path)

    def test_docx(self):
        path = self.root/"test.docx"
        from xml.sax.saxutils import escape
        paragraphs = "".join("<w:p><w:r><w:t>"+escape(line)+"</w:t></w:r></w:p>" for line in self.text.splitlines())
        with zipfile.ZipFile(path,"w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+paragraphs+'<w:tbl><w:tr><w:tc><w:p><w:r><w:t>table evidence</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        self.assertEqual(self.check(path)["pages"][0]["tables"], [[["table evidence"]]])

    def pdf(self, scan=False):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF unavailable")
        path=self.root/("scan.pdf" if scan else "test.pdf")
        with fitz.open() as document:
            page=document.new_page()
            page.insert_text((50,50),self.text,fontsize=18)
            if scan:
                pix=page.get_pixmap(matrix=fitz.Matrix(2,2))
                with fitz.open() as raster:
                    raster.new_page().insert_image(page.rect,pixmap=pix)
                    raster.save(path)
            else:
                document.save(path)
        return path

    def test_pdf(self):
        self.check(self.pdf())

    @unittest.skipUnless(shutil.which("tesseract"),"Tesseract unavailable")
    def test_scanned_pdf(self):
        path=self.pdf(scan=True)
        self.assertFalse(extract(path)["pages"][0]["text"].strip())
        self.assertEqual(self.check(path,True)["pages"][0]["method"],"local OCR")

    def test_missing_pdf_dependency_preserves_txt(self):
        path=self.root/"missing.pdf"
        path.write_bytes(b"PDF fixture")
        text=self.root/"test.txt"
        text.write_text(self.text,encoding="utf-8")
        with patch.dict(sys.modules,{"fitz":None}):
            with self.assertRaisesRegex(ValueError,"install requirements-documents.txt"):
                extract(path)
            self.check(text)

    def test_missing_ocr_preserves_text_layer_intake(self):
        path=self.pdf(scan=True)
        with patch("sds_intake.shutil.which",return_value=None):
            with self.assertRaisesRegex(ValueError,"Tesseract on PATH"):
                extract(path,True)
            self.assertFalse(extract(path)["pages"][0]["text"].strip())
