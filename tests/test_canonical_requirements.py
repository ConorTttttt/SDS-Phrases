import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import canonical_requirements as c

class CanonicalTests(unittest.TestCase):
    def test_canonical_schema(self):
        pack,raw,_=c.load()
        self.assertEqual(len(raw),597)
        self.assertEqual([json.loads(x) for x in (c.ROOT/"regulatory/canonical/requirements.jsonl").read_text(encoding="utf-8").splitlines()],pack["requirements"])
        self.assertTrue(all(r["implementation_status"]=="manual_review_only" for r in pack["requirements"]))
        self.assertEqual(len({r["id"] for r in pack["requirements"]}),len(pack["requirements"]))
    def test_canonical_legacy_map(self):
        pack,raw,_=c.load()
        self.assertEqual(len(pack["migration"]),597)
        self.assertTrue(any(not m["requirement_ids"] for m in pack["migration"]))
        self.assertEqual(c.coverage(pack,raw)["1"]["coverage"],"incomplete")
        self.assertEqual(c.evaluate_requirement(pack["requirements"][0])["status"],"Insufficient evidence")
    def test_roundtrip(self):
        pack,_,_=c.load()
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)
            db=c.build(out)
            self.assertEqual([json.loads(x) for x in (out/"requirements.jsonl").read_text().splitlines()],pack["requirements"])
            self.assertTrue(c.search(db,"nanoform"))
            self.assertTrue(c.retrieve_clause(db,"Annex II Part A 1.1")["requirements"])
            self.assertTrue(c.resolve_legacy(pack,"annex/2")["requirement_ids"])
            self.assertEqual(c.read(out/"requirements.json"),pack)
    def test_version(self):
        pack,_,_=c.load()
        r=pack["requirements"][0]
        self.assertEqual(c.requirement_version(r),c.requirement_version(dict(reversed(list(r.items())))))
        self.assertNotEqual(c.requirement_version(r),c.requirement_version(dict(r,wording="changed")))

    def test_expanded_coverage_and_roles(self):
        pack,raw,_=c.load()
        coverage=c.coverage(pack,raw)
        self.assertEqual(set(coverage),{str(i) for i in range(17)})
        self.assertTrue(all(v["requirements"] and v["coverage"]=="incomplete" for v in coverage.values()))
        self.assertEqual(sum(v["source_records"] for v in coverage.values()),597)
        self.assertEqual(pack["source_annotations"]["annex/516"]["corrected_clause"],"11.2")
        self.assertEqual(pack["source_annotations"]["annex/564"]["continuation"],"annex/566")
        self.assertEqual(c.resolve_legacy(pack,"annex/565")["source_role"],"footnote")
        self.assertEqual(c.resolve_legacy(pack,"annex/99")["source_role"],"table_material")
        self.assertEqual(c.resolve_legacy(pack,"annex/450")["source_role"],"example_or_optional_reference")
        rows={r["id"]:r for r in pack["requirements"]}
        self.assertNotIn("IATA, 2007",rows["EU-REACH-AII-TRANSPORT-SHIPPING-NAME"]["wording"])
        self.assertIn("If the UN number",rows["EU-REACH-AII-TRANSPORT-SHIPPING-NAME"]["wording"])

    def test_archived_version_and_ref11_links(self):
        pack,raw,_=c.load()
        old=pack["historical_versions"][0]["record"]
        active=next(r for r in pack["requirements"] if r["id"]==old["id"])
        self.assertNotEqual(c.requirement_version(old),c.requirement_version(active))
        self.assertEqual(c.resolve_requirement_version(pack,old["id"],c.requirement_version(old)),old)
        self.assertNotIn("explosion limit",active["wording"])
        self.assertEqual(pack["source_annotations"]["annex/336"]["corrected_clause"],"9.1(g)")
        self.assertTrue(c.inspection_link(pack,"REF11/3.8")["requirement_ids"])
        self.assertEqual(c.inspection_link(pack,"REF11/3.4")["link_status"],"partial_link_external_legal_basis_unresolved")
        self.assertFalse(c.inspection_link(pack,"REF11/0.1")["requirement_ids"])
        self.assertFalse(any(m["disposition"]=="pending_decomposition" for m in pack["migration"]))
