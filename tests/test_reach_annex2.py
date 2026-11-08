"""REACH Annex II structural audits and source-parser boundaries.

Fixtures contain no copied legal text. Every outcome remains draft-only.
"""
import copy
import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from reach_annex2_audit import ReachAuditError,audit_structure,load_structure
from reach_annex2_source import _pages,ReachSourceError
from server import create_handler

def product(**values):
    base={"jurisdiction":"EU","as_of":"2026-11-08",
          "product_type":{"value":"mixture","evidence":"Synthetic type evidence"},
          "inventory_complete":{"value":"yes","evidence":"Synthetic heading export"},
          "headings":[],"blank_subsections":[]}
    base.update(values)
    return base

def outcome(results,code):
    return next(item for item in results["outcomes"] if item["code"]==code)

def expected(kind="mixture"):
    schema=load_structure()
    return [item["code"] for sec in schema["sections"]
            for item in [sec,*sec["subsections"]]
            if item["code"]!=("3.1" if kind=="mixture" else "3.2")]

class ReachStructureTests(unittest.TestCase):
    def test_16_sections_51_subsections(self):
        s=load_structure()
        self.assertEqual(len(s["sections"]),16)
        self.assertEqual(sum(len(x["subsections"]) for x in s["sections"]),51)
        self.assertEqual(s["source"]["consolidated_edition"],"2026-06-22")
        self.assertNotIn("legal_effective_date",s["source"])

    def test_full_reported_mixture_heading_inventory(self):
        r=audit_structure(product(headings=expected()))
        self.assertEqual(r["counts"]["reported_present"],66)
        self.assertEqual(r["counts"]["not_expected_for_product_type"],1)
        self.assertNotIn("reported_missing",r["counts"])
        self.assertFalse(r["sds_compliant"])
        self.assertFalse(r["subsection_content_validated"])

    def test_substance_section3_alternative(self):
        r=audit_structure(product(
            product_type={"value":"substance","evidence":"Synthetic identity"},
            headings=expected("substance")))
        self.assertEqual(outcome(r,"3.1")["decision"],"reported_present")
        self.assertEqual(outcome(r,"3.2")["decision"],"not_expected_for_product_type")

    def test_unknown_product_does_not_assume_section3_exclusion(self):
        p=product(headings=expected(),
                  product_type={"value":"mixture","evidence":""})
        r=audit_structure(p)
        self.assertEqual(outcome(r,"3.1")["decision"],"product_type_required")
        self.assertEqual(outcome(r,"3.2")["decision"],"product_type_required")
        self.assertEqual(r["product_type_evidenced"],"unknown")

    def test_missing_unambiguous_heading_with_complete_inventory(self):
        h=[code for code in expected() if code!="4.1"]
        r=audit_structure(product(headings=h))
        self.assertEqual(outcome(r,"4.1")["decision"],"reported_missing")

    def test_incomplete_or_unevidenced_inventory_does_not_assert_absence(self):
        for val,evidence in (("unknown",""),("yes",""),("no","not complete")):
            p=product(inventory_complete={"value":val,"evidence":evidence})
            with self.subTest(profile=p):
                self.assertEqual(outcome(audit_structure(p),"4.1")["decision"],"information_required")

    def test_reported_blank_is_flagged_without_choosing_substitute_phrase(self):
        r=audit_structure(product(headings=expected(),blank_subsections=["4.2"]))
        self.assertEqual(outcome(r,"4.2")["decision"],"reported_blank")
        self.assertFalse(r["sds_compliant"])

    def test_unrecognised_heading_retained(self):
        p=product(headings=expected()+["9.9"])
        r=audit_structure(p)
        self.assertEqual(r["unrecognised_heading_codes"],["9.9"])

    def test_version_warning_earlier_date(self):
        p=product(as_of="2024-11-01",headings=expected())
        self.assertIsNotNone(audit_structure(p)["source_edition_warning"])

    def test_input_validation(self):
        cases=[
            product(jurisdiction="US"),
            product(as_of="2026-02-30"),
            product(headings=["4.1","4.1"]),
            product(headings=["4.1; DROP TABLE"]),
            product(blank_subsections=["4","4.1"]),
            product(product_type={"value":"liquid","evidence":"test"}),
        ]
        for p in cases:
            with self.subTest(p=p),self.assertRaises(ReachAuditError):
                audit_structure(p)

    def test_parser_requires_all_36_pages_and_markers(self):
        pages=["PDF page"]*36
        pages[0]="ANNEX II PART A"
        pages[7]="Table 1.1"
        pages[33]="PART B SECTION 1"
        pages[35]="SECTION 16: Other information"
        self.assertEqual(len(_pages("\f".join(pages)+"\f")),36)
        with self.assertRaises(ReachSourceError):
            _pages("\f".join(pages[:35])+"\f")
        pages[33]="Wrong part"
        with self.assertRaises(ReachSourceError):
            _pages("\f".join(pages)+"\f")

class ReachHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),create_handler(ROOT/"no-such-file.sqlite"))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
    def req(self,method,path,payload=None):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            body=json.dumps(payload) if payload is not None else None
            headers={"Content-Type":"application/json"} if body is not None else {}
            c.request(method,path,body=body,headers=headers)
            res=c.getresponse();status=res.status
            data=res.read().decode("utf8")
            return status,json.loads(data) if path.startswith("/api/") else data
        finally:c.close()
    def test_structure_and_inventory_available_without_phrase_db(self):
        code,structure=self.req("GET","/api/reach/structure")
        self.assertEqual(code,200)
        self.assertEqual(len(structure["sections"]),16)
        code,inventory=self.req("GET","/api/reach/content-inventory")
        self.assertEqual(code,200)
        self.assertFalse(inventory["executable"])
        self.assertGreaterEqual(len(inventory["items"]),20)
    def test_audit_api_fails_closed(self):
        code,r=self.req("POST","/api/reach/audit",product(headings=expected()))
        self.assertEqual(code,200)
        self.assertFalse(r["sds_compliant"])
        code,r=self.req("POST","/api/reach/audit",{"jurisdiction":"GB"})
        self.assertEqual(code,400)
        self.assertIn("error",r)
    def test_page_browser_is_served(self):
        code,body=self.req("GET","/reach.html")
        self.assertEqual(code,200)
        self.assertIn("REACH Annex II",body)

if __name__=="__main__":
    unittest.main()
