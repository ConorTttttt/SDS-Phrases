import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import canonical_requirements as c

class CLPCanonicalTests(unittest.TestCase):
    def setUp(self):
        self.pack=c.load_clp()
        self.rows={r["id"]:r for r in self.pack["requirements"]}
    def test_clp_schema(self):
        self.assertEqual(len(self.rows),len(self.pack["requirements"]))
        self.assertTrue(all(r["implementation_status"]=="manual_review_only" for r in self.rows.values()))
        self.assertTrue(all(r["effective_date"] is None for r in self.rows.values()))
        self.assertTrue(self.pack["coverage_gaps"])
        self.assertEqual(c.clp_coverage(self.pack)["coverage"],"candidate_partial")
    def test_ufi_distinctions(self):
        self.assertIn("or be included",self.rows["EU-CLP-VIII-A-UFI-UNPACKAGED"]["wording"])
        self.assertEqual(self.rows["EU-CLP-VIII-A-UFI-INDUSTRIAL"]["modality"],"permitted_alternative")
        self.assertIn("EU-REACH-AII-UFI-LOCATION",self.rows["EU-CLP-VIII-A-UFI-INDUSTRIAL"]["related_requirements"])
        self.assertIn("exceeding 0,1 %",self.rows["EU-CLP-A25-BESPOKE-UFI"]["wording"])
        self.assertIn("exceeds 5 %",self.rows["EU-CLP-A25-BESPOKE-CONCENTRATION"]["wording"])
        self.assertIn("not blanket SDS",self.rows["EU-CLP-VIII-B-EMERGENCY-CONTACT"]["required_sds_content"])
    def test_precedence_and_unverified_evidence(self):
        row=self.rows["EU-CLP-A26-CORROSION"]
        self.assertIn("for skin or eye irritation",row["wording"])
        self.assertIn("unrelated hazards",row["exceptions"][0])
        for r in self.rows.values():
            self.assertFalse(c.evaluate_requirement(r,{"text":"present"})["deterministic"])
            self.assertNotEqual(c.evaluate_requirement(r,{"text":"present"})["status"],"Compliant against assessed requirement")
    def test_table4_reference(self):
        t=self.pack["reference_tables"][0]
        self.assertEqual(t["execution"],"reference_only")
        self.assertEqual([x["relative_variation_percent"] for x in t["rows"]],[5,10,20,30])
        self.assertFalse(t["rows"][0]["lower_inclusive"])
        self.assertTrue(t["rows"][0]["upper_inclusive"])
    def test_historical_versions_and_source_check(self):
        self.assertEqual(len(self.pack["historical_versions"]),6)
        self.assertEqual(self.pack["source_text_check"]["matched"],len(self.pack["source_records"]))
        for entry in self.pack["historical_versions"]:
            old=entry["record"]
            self.assertNotEqual(c.requirement_version(old),c.requirement_version(self.rows[old["id"]]))
            self.assertEqual(c.resolve_any_requirement_version(old["id"],c.requirement_version(old)),old)
    def test_sqlite_and_combined(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            db=c.build(out)
            rows=[json.loads(line) for line in (out/"all_requirements.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows,c.all_requirements())
            r=self.rows["EU-CLP-A20-DANGER-PRECEDENCE"]
            self.assertEqual(c.resolve_any_requirement_version(r["id"],c.requirement_version(r)),r)
            self.assertTrue(c.retrieve_clause(db,"Article 20(3)")["requirements"])
            self.assertTrue(c.retrieve_clause(db,"Article 20(3)")["source_records"])
