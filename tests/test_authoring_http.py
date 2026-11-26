"""Exercise the unmocked local authoring routes without a licensed catalogue."""
import base64
import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from test_sds_authoring import product

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from server import create_handler


class AuthoringHTTP(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.catalogue=Path(tmp.name)/"absent.sqlite"
        server=ThreadingHTTPServer(("127.0.0.1",0),create_handler(self.catalogue))
        self.server=server
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(thread.join,5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, action, payload, expected=200, authorised=True):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=30)
        headers={"Content-Type":"application/json"}
        if authorised:
            headers["X-SDS-Local-Review"]="1"
        try:
            c.request("POST","/api/authoring/"+action,json.dumps(payload),headers)
            res=c.getresponse()
            data=json.loads(res.read())
            self.assertEqual(res.status,expected,data)
            return data
        finally:
            c.close()

    def test_authoring_without_catalogue(self):
        self.request("schema",{},403,False)
        self.assertIn("headings",self.request("schema",{}))
        self.request("catalogue",{"query":"fixture"},400)
        dossier={"products":[product()],"content":[]}
        report=self.request("evaluate",{"dossier":dossier})
        self.assertTrue(report["products"][0]["findings"])
        phrase={"kind":"internal","wording":"Synthetic only.","subsection":"7.1","status":"approved",
                "reviewer":"QA","reason":"synthetic fixture","jurisdiction":"EU","language":"en",
                "conditions":{"properties":{"physical_state":"liquid"}}}
        approval=self.request("approve-phrase",{"phrase":phrase})
        self.assertTrue(any(p["id"]==approval["id"] for p in self.request("phrases",{})))
        dossier["content"]=[{"id":"sample","code":"7.1","kind":"internal","wording":phrase["wording"],
            "products":["A"],"status":"approved","reviewer":"QA","reason":"fixture",
            "approval_id":approval["id"],"approval_version":approval["version"]}]
        saved=self.request("save",{"case_id":"fixture","dossier":dossier})
        self.assertEqual(saved["version"],1)
        rejected=self.request("approve-phrase",{"phrase":dict(phrase,id=approval["id"],expected_version=1,status="rejected")})
        self.assertEqual(rejected["status"],"rejected")
        updated=self.request("evaluate",{"dossier":dossier})
        self.assertNotEqual(saved["report"]["fingerprint"],updated["fingerprint"])
        self.assertTrue(any("sample" in row["invalid_blocks"] for row in updated["products"][0]["rows"]))
        second=self.request("save",{"case_id":"fixture","dossier":dossier,"expected_version":1})
        self.assertEqual(second["version"],2)
        self.request("save",{"case_id":"fixture","dossier":dossier,"expected_version":1},400)
        self.assertEqual(len(self.request("history",{"case_id":"fixture"})),2)
        self.assertIn("diff",self.request("compare",{"case_id":"fixture","left":1,"right":2}))
        payload={"case_id":"fixture","version":2,"format":"json"}
        data=base64.b64decode(self.request("export",payload)["base64"])
        self.assertIn(b"NOT FOR SUPPLY",data)
        self.request("export",dict(payload,version=99),400)
        self.request("does-not-exist",{},404)
        self.assertFalse(self.catalogue.exists())
