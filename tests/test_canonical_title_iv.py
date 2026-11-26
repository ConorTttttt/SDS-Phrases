import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import canonical_requirements as c

class TitleIVTests(unittest.TestCase):
    def test_schema_and_source_trace(self):
        pack=c.load_title_iv()
        rows={r["id"]:r for r in pack["requirements"]}
        self.assertTrue(all(r["implementation_status"]=="manual_review_only" for r in rows.values()))
        self.assertEqual(set(c.title_iv_coverage(pack)),{str(i) for i in range(31,37)})
        self.assertTrue(all(v["requirements"] for v in c.title_iv_coverage(pack).values()))
        self.assertFalse(any(r["clause"]=="Article 31(10)" for r in rows.values()))
        self.assertEqual(c.evaluate_requirement(rows["EU-REACH-A31-REQUEST-OEL"])["status"],"Insufficient evidence")
    def test_threshold_distinction(self):
        rows={r["id"]:r for r in c.load_title_iv()["requirements"]}
        self.assertIn("no concentration threshold",rows["EU-REACH-A31-REQUEST-OEL"]["exceptions"][0])
        self.assertIn("≥0.1% w/w",rows["EU-REACH-A31-REQUEST-PBT"]["applicability_conditions"])
        self.assertIn(">0.1% w/w",rows["EU-REACH-A33-ARTICLE-RECIPIENT"]["applicability_conditions"])
        self.assertIn("45 days",rows["EU-REACH-A33-CONSUMER-DEADLINE"]["required_sds_content"])
    def test_sqlite_and_export(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)
            db=c.build(out)
            rows=[json.loads(l) for l in (out/"all_requirements.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows,c.all_requirements())
            self.assertTrue(c.retrieve_clause(db,"Article 31(3)(c)")["requirements"])
            self.assertTrue(c.retrieve_clause(db,"Article 31(3)(c)")["source_records"])
