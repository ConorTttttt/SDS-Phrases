"""Offline HTTP and source checks without proprietary fixtures."""
import hashlib
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"scripts")]
import server
import build_gemini_package
from reach_annex2_source import import_pdf, ReachSourceError

class OfflineHTTP(unittest.TestCase):
    def test_routes_without_local_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.multiple(server,GUIDANCE_DB=root/"guidance.sqlite",REACH_DB=root/"reach.sqlite",REVIEWS=root/"reviews.sqlite"):
                httpd=ThreadingHTTPServer(("127.0.0.1",0),server.create_handler(root/"missing.sqlite"))
                t=threading.Thread(target=httpd.serve_forever,daemon=True)
                t.start()
                def request(method,path,headers=None):
                    c=http.client.HTTPConnection("127.0.0.1",httpd.server_port,timeout=10)
                    try:
                        c.request(method,path,headers=headers or {})
                        r=c.getresponse()
                        return r.status,r.read()
                    finally:
                        c.close()
                try:
                    for path in server.STATIC:
                        with self.subTest(path=path):
                            status,body=request("GET",path)
                            self.assertEqual(status,200)
                            self.assertTrue(body)
                    for path in ("info","rules","regulatory/pack","reach/structure","reach/content-inventory","readiness/prompts","section-recommendations/config","profile-recommendations/families"):
                        with self.subTest(path=path):
                            status,body=request("GET","/api/"+path)
                            self.assertEqual(status,200)
                            self.assertIsInstance(json.loads(body),(dict,list))
                    for path in ("search","catalogue/summary","catalogue/search","guidance/summary","guidance/search","reach/source/summary","reach/source/search","phrase-finder/sections","phrase-finder/search"):
                        with self.subTest(path=path):
                            status,body=request("GET","/api/"+path)
                            self.assertEqual(status,503)
                            self.assertTrue(json.loads(body)["error"])
                    for path in ("evaluate","regulatory/evaluate","reach/audit","readiness/evaluate","section-recommendations/evaluate","profile-recommendations/evaluate","phrase-finder/validate-draft"):
                        with self.subTest(path=path):
                            status,body=request("POST","/api/"+path,{"Content-Type":"application/json"})
                            self.assertEqual(status,413)
                            self.assertIn("error",json.loads(body))
                    self.assertEqual(request("POST","/api/catalogue/review")[0],403)
                    self.assertEqual(request("GET","/api/no-such-route")[0],404)
                    self.assertFalse(json.loads(request("GET","/api/info")[1])["catalogue_installed"])
                    self.assertFalse((root/"missing.sqlite").exists())
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    t.join(5)

class SourceChecks(unittest.TestCase):
    def test_manifest_links(self):
        manifest=json.loads((ROOT/"regulatory/source_manifest.json").read_text())
        for field in ("id","filename","package_filename"):
            values=[s[field] for s in manifest["sources"]]
            self.assertEqual(len(values),len(set(values)))
        self.assertEqual(len(manifest["sources"]),5)
        for s in manifest["sources"]:
            self.assertRegex(s["sha256"],r"^[0-9a-f]{64}$")
            self.assertGreater(s["pages"],0)
        for p in ("ANNEX_II_STRUCTURE_AND_GATES.md","ECHA_SECTION_PLAYBOOK.md","PHRASE_NOTEBOOK_SPEC.md","PRODUCT_BRIEF.md","REACH_REGULATORY_DECISIONS.md","REF11_AUDIT_WORKFLOW.md","REGULATORY_SOURCE_REGISTER.md"):
            self.assertTrue((ROOT/"regulatory/author/references"/p).is_file(),p)
    def test_missing_or_tampered_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for tampered in (False,True):
                if tampered: (p/"Full REACH.pdf").write_bytes(b"not the pinned PDF")
                with self.assertRaisesRegex(ValueError,"Missing or changed pinned source"):
                    build_gemini_package.build(p,p/"result")
                self.assertFalse((p/"result").exists())
            with self.assertRaises(ReachSourceError):
                import_pdf(p/"Full REACH.pdf",p/"reach.sqlite")
            self.assertFalse((p/"reach.sqlite").exists())
    @unittest.skipUnless(os.getenv("SDS_SOURCE_DIR"),"Local pinned PDFs not provisioned")
    def test_actual_sources_and_package(self):
        source=Path(os.environ["SDS_SOURCE_DIR"])
        manifest=json.loads((ROOT/"regulatory/source_manifest.json").read_text())
        for s in manifest["sources"]:
            self.assertEqual(hashlib.sha256((source/s["filename"]).read_bytes()).hexdigest(),s["sha256"])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            build_gemini_package.build(source,p/"gemini")
            self.assertTrue((p/"gemini/author/SKILL.md").is_file())
            self.assertFalse(any((p/"gemini").rglob("*.sqlite")))
            self.assertEqual(import_pdf(source/"Full REACH.pdf",p/"reach.sqlite")["pages"],36)
