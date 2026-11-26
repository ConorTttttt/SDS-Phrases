import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sds_authoring import (PhraseApprovals, Workspace, digest, profile_inputs, validate_dossier,
                           evidence, gates, draft_text, export_draft, catalogue_row)

def product(pid="A"):
    return {"id":pid,"kind":"mixture","jurisdiction":"EU","language":"en","as_of":"2026-06-22",
            "sources":{"s":{"reference":"test fixture","locator":"p1","version":"1"}},
            "data":{"formulation":{"value":[{"identity":"test","mass_percent":100}],"sources":["s"]},
                    "mixture_classification":{"value":{"hazards":["H225"],"complete":True},"sources":["s"]},
                    "properties":{"value":{"physical_state":"liquid"},"sources":["s"]}}}

class TestAuthoring(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cat=self.root/"catalogue.sqlite"
        with sqlite3.connect(self.cat) as db:
            db.execute("""CREATE TABLE entries(entry_key,catalogue_version,collection,source_file,
                excel_row,structurecode,esdscom_phrase_id,original_code,english,jurisdiction_structure,sds_section)""")
            db.execute("CREATE TABLE catalogue_index(entry_key,wording_hash,sds_subsection,phrase_kind)")
            db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       ("fixture","5.5","Core","fixture.xlsx",1,"fixture",None,None,"Fixture text.","EU",7))
            db.execute("INSERT INTO catalogue_index VALUES (?,?,?,?)",("fixture","fixture-hash","7.1","sentence"))
        db.close()
        self.ap=PhraseApprovals(self.root/"approvals.sqlite",self.cat)
    def record(self):
        return {"kind":"catalogue","entry_key":"fixture","wording":"Fixture text.","subsection":"7.1",
                "status":"approved","reviewer":"test reviewer","reason":"fixture only","jurisdiction":"EU","language":"en",
                "conditions":{"properties":{"physical_state":"liquid"}}}
    def test_provenance_and_immutability(self):
        before=hashlib.sha256(self.cat.read_bytes()).hexdigest()
        approved=self.ap.save(self.record())
        self.assertIsNone(approved["source"]["esdscom_phrase_id"])
        self.assertTrue(approved["id"].startswith("INT-"))
        self.assertEqual(before,hashlib.sha256(self.cat.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            self.ap.save(dict(self.record(),wording="Modified"))
    def test_revocation_and_conditions(self):
        a=self.ap.save(self.record())
        self.assertTrue(self.ap.valid(a,product(),"7.1"))
        p=product()
        p["data"]["properties"]["value"]["physical_state"]="solid"
        self.assertFalse(self.ap.valid(a,p,"7.1"))
        b=self.ap.save(dict(self.record(),id=a["id"],expected_version=1,status="rejected"))
        self.assertFalse(self.ap.valid(b,product(),"7.1"))
    def test_missing_evidence_and_mass_balance(self):
        p=product()
        p["data"]["properties"]["sources"]=[]
        self.assertFalse(evidence(p,"properties"))
        self.assertNotIn("physical_state",profile_inputs(p)[0])
        p["data"]["formulation"]["value"][0]["mass_percent"]=50
        with self.assertRaises(ValueError):
            validate_dossier({"products":[p]})
    def test_classification_change_invalidates_fingerprint(self):
        p=product()
        h=digest(p)
        p["data"]["mixture_classification"]["value"]["hazards"]=["H318"]
        self.assertEqual(profile_inputs(p)[0]["hazards"],["H318"])
        self.assertNotEqual(h,digest(p))
        self.assertTrue(gates({"fingerprint":digest(p)},{"fingerprint":h}))
    def test_group_no_hazard_shortcut(self):
        a,b=product(),product("B")
        b["data"]["properties"]["value"]["physical_state"]="solid"
        dossier={"products":[a,b],"content":[{"id":"x","code":"9.1","kind":"fact","wording":"Liquid",
                         "products":["A"],"status":"approved"}]}
        self.assertIn("Liquid",draft_text(dossier,a))
        self.assertNotIn("Liquid",draft_text(dossier,b))
        self.assertIn("INFORMATION GAP",draft_text(dossier,b))
    def test_conflict_gate(self):
        report={"fingerprint":"x","products":[{"product":"A","errors":[],"conflicts":["contradictory state"],
                "rows":[],"findings":[]}]}
        self.assertTrue(any("contradictory state" in g for g in gates(report,{"fingerprint":"x"})))
    def test_revision_and_draft_export(self):
        w=Workspace(self.root/"workspace.sqlite",self.ap)
        d={"products":[product()],"content":[]}
        with patch("sds_authoring.evaluate",return_value={"fingerprint":"test","products":[]}):
            r=w.save("case",d)
            w.save("case",d,1)
            with self.assertRaises(ValueError):
                w.save("case",d,1)
        self.assertEqual(len(w.history("case")),2)
        self.assertIn(b"NOT FOR SUPPLY",export_draft(r,"json"))

if __name__=="__main__":
    unittest.main()
