import copy
import unittest
from exchange import DIMENSIONS, prepare, validate


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(id="annex/0", section="1", document_sha256="a"*64, product_evidence="private")]
        self.bundle = prepare(self.rows, "P", ["annex/0:section"])
        self.reply = {k:v for k,v in self.bundle.items() if k!="evidence"}
        self.reply["findings"] = [dict(requirement_id="annex/0", evidence_ids=["annex/0:section"],
            source_id="reach", citation="Annex II", status="Insufficient evidence",
            interpretation="Only the heading was supplied", requested_action="Request the original",
            **dict.fromkeys(DIMENSIONS,"unresolved"))]

    def test_selection(self):
        self.assertNotIn("private", str(self.bundle))
        self.assertEqual(prepare(self.rows,"P",[])["evidence"],[])
        self.assertIn("pending",validate(self.rows,self.bundle,self.reply,"P")["review_status"])

    def test_mismatches(self):
        for k,v in [("product_id","Q"),("sources",{}),("document_sha256","b"*64),("export_id","bad")]:
            with self.subTest(k=k), self.assertRaises(ValueError):
                validate(self.rows,self.bundle,dict(self.reply,**{k:v}),"P")
        for k,v in [("requirement_id","unknown"),("source_id","legacy"),("evidence_ids",["private"])]:
            reply=copy.deepcopy(self.reply)
            reply["findings"][0][k]=v
            with self.subTest(k=k), self.assertRaises(ValueError):
                validate(self.rows,self.bundle,reply,"P")
