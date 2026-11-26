import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from toolkit import assess, article31
class ToolkitTests(unittest.TestCase):
    def fixture(self):
        return json.loads((ROOT/"regulatory/example.synthetic.json").read_text())
    def test_unknown_not_pass(self):
        f=self.fixture(); f.pop("hazardous"); f.pop("structure")
        report=assess(f)
        self.assertEqual(report["article31"]["status"],"insufficient_evidence")
        self.assertFalse(report["legal_compliance_determined"])
    def test_positive_review_only(self):
        self.assertEqual(article31(self.fixture())["status"],"requires_competent_person_review")
    def test_nonclassified_mixture_not_assessed(self):
        f=self.fixture(); f["hazardous"]["value"]="no"
        self.assertEqual(article31(f)["status"],"not_assessed")
    def test_unsupported_jurisdiction(self):
        f=self.fixture(); f["jurisdiction"]="GB"
        with self.assertRaises(ValueError): article31(f)
    def test_structure_is_not_compliance(self):
        self.assertFalse(assess(self.fixture())["structure"]["sds_compliant"])
    def test_copied_section9_parity(self):
        self.assertEqual((ROOT/"modules/section9/rules.mjs").read_bytes(),(ROOT/"web/section9-rules.js").read_bytes())
