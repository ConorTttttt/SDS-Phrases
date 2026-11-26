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
