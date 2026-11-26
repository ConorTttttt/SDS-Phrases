import csv
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sds_intake import extract
from sds_assessment import assess, export, UNKNOWN, SUSPECT

class SupplierAssessment(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.source=self.root/"supplier.txt"
        self.source.write_text("SECTION 2: Hazards\n2.1 Classification\nH225\fSECTION 9: Properties\n9.1 Basic properties\nFlammability: Non-flammable")
        self.doc=extract(self.source)

    def test_conflict_cites_both_pages(self):
        rows={r["id"]:r for r in assess(self.doc)}
        self.assertEqual(rows["conflict/flammability"]["status"],SUSPECT)
        self.assertEqual(rows["conflict/flammability"]["page"],"1, 2")
        self.assertEqual(rows["heading/3.2"]["status"],UNKNOWN)

    def test_correction_keeps_original(self):
        rows={r["id"]:r for r in assess(self.doc,{"1":"SECTION 9: Properties\n9.1 Basic properties\nFlammable"})}
        self.assertNotIn("conflict/flammability",rows)
        self.assertIn("Non-flammable",rows["heading/9.1"]["original_wording"])
        self.assertIn("Flammable",rows["heading/9.1"]["product_evidence"])

    def test_reports(self):
        rows=assess(self.doc)
        export(self.root,self.doc,rows)
        with (self.root/"findings.csv").open(encoding="utf-8-sig") as f:
            self.assertEqual(len(list(csv.DictReader(f))),len(rows))
        self.assertIn("flash point",(self.root/"corrective-actions.txt").read_text())
        self.assertIn("supplier.txt",(self.root/"report.html").read_text())

    def test_docx(self):
        path=self.root/"example.docx"
        with zipfile.ZipFile(path,"w") as z:
            z.writestr("word/document.xml",'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>H225</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        p=extract(path)["pages"][0]
        self.assertIsNone(p["page"])
        self.assertEqual(p["tables"],[[["H225"]]])

    def test_structured_empty_page(self):
        p=self.root/"scan.json"
        p.write_text(json.dumps({"pages":[{"page":14,"text":""}]}))
        rows=assess(extract(p))
        self.assertTrue(all(r["status"]==UNKNOWN for r in rows if r["id"].startswith("heading/")))

    def test_pdf_and_local_ocr(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF optional dependency unavailable")
        source=self.root/"scan.pdf"
        with fitz.open() as pdf:
            page=pdf.new_page()
            page.insert_text((72,80),"SECTION 2: Hazards",fontsize=20)
            image=page.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes("png")
            scan=pdf.new_page()
            scan.insert_image(scan.rect,stream=image)
            pdf.save(source)
        doc=extract(source)
        self.assertEqual(doc["pages"][1]["text"].strip(),"")
        self.assertTrue(doc["pages"][1]["image_regions"])
        import shutil
        if shutil.which("tesseract"):
            doc=extract(source,ocr=True)
            self.assertIn("SECTION 2",doc["pages"][1]["text"])
            self.assertEqual(doc["pages"][1]["page"],2)

    def test_missing_node_preserves_other_assessment(self):
        from unittest.mock import patch
        self.doc["context"]={"section9":{"state":"liquid","kind":"mixture","aerosol":False}}
        with patch("sds_assessment.shutil.which",return_value=None):
            rows={r["id"]:r for r in assess(self.doc)}
        self.assertEqual(rows["section9/unavailable"]["status"],"Not assessed")
        self.assertTrue(any(k.startswith("REF11/") for k in rows))
        self.assertIn("heading/2",rows)

    def test_verified_heading_inventory(self):
        self.doc["context"]={"verified_structure":{
            "jurisdiction":"EU","as_of":"2026-06-22","headings":["2","2.1","9","9.1"],
            "inventory_complete":{"value":"yes","evidence":"All original pages visually checked"},
            "product_type":{"value":"mixture","evidence":"Synthetic formulation"}}}
        rows={r["id"]:r for r in assess(self.doc)}
        self.assertEqual(rows["heading/3.1"]["status"],"Not applicable")
        self.assertEqual(rows["heading/3.2"]["status"],"Non-compliant")

    def test_health_conflict_and_english_wording(self):
        self.doc["pages"][0]["text"]+="\nH318 Causes serious eye damage.\nSECTION 4: First aid\n4.1 Description\nEye contact: no action required"
        rows={r["id"]:r for r in assess(self.doc)}
        self.assertEqual(rows["conflict/first-aid"]["status"],SUSPECT)
        self.assertEqual(rows["wording/H318"]["presence"],"reference wording located")
        self.assertIn("287",rows["wording/H318"]["source_citation"])

    def test_physical_impossibility(self):
        self.doc["pages"][1]["text"]+="\nKinematic viscosity: -1 mm²/s"
        rows=[r for r in assess(self.doc) if r["id"].startswith("property/")]
        self.assertEqual(len(rows),1)
        self.assertIn("9.1(l)",rows[0]["source_citation"])
        self.assertEqual(rows[0]["scientific_plausibility"],SUSPECT)
