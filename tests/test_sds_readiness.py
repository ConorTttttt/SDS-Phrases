"""Synthetic, source-safe tests for ECHA guidance PDF verification and SDS evidence pilot."""
import http.client
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from guidance_pdf_verification import (
    OriginalPDFError, SECTION_START, _page_anchor_audit, verify_original
)
from sds_readiness import ReadinessError, evaluate_readiness, load_prompts
from server import create_handler

PACK=load_prompts()

def profile(**changes):
    out={"jurisdiction":"EU","as_of":"2026-11-08","evidence":{}}
    out.update(changes)
    return out

def response(result,id):
    return next(p for s in result["sections"] for p in s["prompts"] if p["id"]==id)


class GuidanceReadinessTests(unittest.TestCase):
    def test_pilot_has_source_traces_without_regulatory_approval(self):
        self.assertEqual(len(PACK["prompts"]),27)
        self.assertEqual({x["section"] for x in PACK["prompts"]},{4,7,8})
        self.assertEqual(PACK["guidance"]["pages"],137)
        self.assertEqual(PACK["guidance"]["original_pdf_sha256"],
            "2a4ac00f87544ebc6397e208e13da331a5ebabd6c5ceb5f149e84cb138501c28")
        self.assertTrue(all(x["legal_status"]=="not_verified" for x in PACK["prompts"]))
        self.assertTrue(all(x["source"]["guidance_pages"][0]<=x["source"]["guidance_pages"][1]
                            for x in PACK["prompts"]))

    def test_unknown_everything_does_not_suggest_legally_missing_content(self):
        result=evaluate_readiness(profile())
        self.assertEqual(result["counts"]["information_needed"],27)
        self.assertEqual(len(result["sections"]),3)
        self.assertFalse(result["sds_compliant"])
        self.assertFalse(result["content_verified"])
        self.assertFalse(result["legally_applicable_rules_verified"])

    def test_documented_evidence_is_only_submitted_for_review(self):
        first=PACK["prompts"][0]["id"]
        r=evaluate_readiness(profile(evidence={
            first:{"status":"available","reference":"Synthetic first-aid report A1","reason":""}}))
        got=response(r,first)
        self.assertEqual(got["finding"],"evidence_submitted_for_review")
        self.assertFalse(got["content_sufficient"])
        self.assertFalse(got["requirement_legally_verified"])

    def test_no_evidence_reference_remains_unknown(self):
        first=PACK["prompts"][0]["id"]
        r=evaluate_readiness(profile(evidence={
            first:{"status":"available","reference":"", "reason":""}}))
        self.assertEqual(response(r,first)["finding"],"information_needed")

    def test_absent_and_inapplicable_claims_require_reasons_and_review(self):
        a=PACK["prompts"][0]["id"];b=PACK["prompts"][1]["id"]
        result=evaluate_readiness(profile(evidence={
            a:{"status":"not_available","reason":"Synthetic source not available"},
            b:{"status":"not_applicable","reason":"Synthetic justification"}
        }))
        self.assertEqual(response(result,a)["finding"],"missing_data_reason_for_review")
        self.assertEqual(response(result,b)["finding"],"non_applicability_claim_for_review")
        self.assertFalse(result["sds_compliant"])

    def test_bad_values_and_unknown_ids_rejected(self):
        a=PACK["prompts"][0]["id"]
        bad=[
            profile(jurisdiction="GB"),profile(as_of="2026-02-30"),
            profile(evidence={"ECHA_FAKE":{"status":"available","reference":"x"}}),
            profile(evidence={a:{"status":"approved","reference":"x"}}),
            profile(evidence={a:{"status":"available","reference":42}}),
            profile(evidence={a:{"status":"available","reference":"x","foo":"bar"}}),
        ]
        for data in bad:
            with self.subTest(data=data),self.assertRaises(ReadinessError):
                evaluate_readiness(data)


class OriginalGuidanceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.dir=Path(self.temp.name)
        self.archive=self.dir/"source.zip"
        self.pages=["Guidance on the compilation of safety data sheets"]*137
        with zipfile.ZipFile(self.archive,"w") as z:
            for sec,start in SECTION_START.items():
                z.writestr(f"extract/SDS_Section_{sec:02d}.md",
                    f'document_id: "echa-sds-guidance-v4-2020-s{sec}"\n'
                    'source_reference: "ECHA-20-H-25-EN"\n'
                    'source_sha256: "2a4ac00f87544ebc6397e208e13da331a5ebabd6c5ceb5f149e84cb138501c28"\n'
                    'authority: "NOT authoritative legislation"\n'
                    f'**ECHA printed page {start}**')
                self.pages[start-1]=f"Guidance on the compilation of safety data sheets {start} 3.{sec} SDS SECTION {sec}"
    def tearDown(self):self.temp.cleanup()

    def test_16_chapter_source_anchors(self):
        matched=_page_anchor_audit(self.pages,self.archive)
        self.assertEqual(len(matched),16)
        self.assertEqual([x["printed_start_page"] for x in matched],
                         [SECTION_START[k] for k in range(1,17)])
        self.assertTrue(all(x["chapter_first_page_matched"] for x in matched))

    def test_wrong_source_page_detected(self):
        self.pages[56]="No chapter 4 heading on this page 57"
        with self.assertRaises(OriginalPDFError):
            _page_anchor_audit(self.pages,self.archive)

    def test_wrong_pdf_fails_closed_before_text_extraction(self):
        file=self.dir/"fake.pdf"
        file.write_bytes(b"untrusted synthetic file")
        with self.assertRaises(OriginalPDFError):
            verify_original(file,self.archive)

    def test_db_update_requires_archive(self):
        file=self.dir/"fake.pdf";file.write_bytes(b"synthetic")
        with self.assertRaises(OriginalPDFError):
            verify_original(file,db_path=self.dir/"fake.db")


class GuidanceReadinessHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),
                                       create_handler(Path("/no/catalogue.sqlite")))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
    def req(self,method,path,body=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            headers={"Content-Type":"application/json"} if body is not None else {}
            conn.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
            r=conn.getresponse()
            data=r.read().decode("utf8")
            return r.status,json.loads(data) if path.startswith("/api/") else data
        finally:conn.close()

    def test_config_and_browser_without_phrase_catalogue(self):
        status,out=self.req("GET","/api/readiness/prompts")
        self.assertEqual(status,200)
        self.assertEqual(len(out["prompts"]),27)
        status,html=self.req("GET","/readiness.html")
        self.assertEqual(status,200)
        self.assertIn("information readiness",html.lower())

    def test_evaluate_and_fail_closed(self):
        status,out=self.req("POST","/api/readiness/evaluate",profile())
        self.assertEqual(status,200)
        self.assertEqual(out["number_of_prompts"],27)
        self.assertFalse(out["sds_compliant"])
        status,out=self.req("POST","/api/readiness/evaluate",{"jurisdiction":"US"})
        self.assertEqual(status,400)
        self.assertIn("error",out)

if __name__=="__main__":
    unittest.main()
