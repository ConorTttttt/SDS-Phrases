"""Local HTTP smoke checks for the independent v0.2 API (no catalogue required)."""
import http.client
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from server import create_handler

class RegulatoryAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd=ThreadingHTTPServer(("127.0.0.1",0),create_handler(Path("/nonexistent/catalogue.sqlite")))
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def request(self,method,path,body=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.httpd.server_port,timeout=5)
        headers={"Content-Type":"application/json"} if body is not None else {}
        try:
            conn.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
            response=conn.getresponse()
            status=response.status
            payload=response.read().decode("utf-8")
            return status,json.loads(payload) if path.startswith("/api/") else payload
        finally:
            conn.close()

    def test_rules_and_browser_available(self):
        status,pack=self.request("GET","/api/regulatory/pack")
        self.assertEqual(status,200)
        self.assertEqual(pack["version"],"0.2.0")
        status,html=self.request("GET","/regulatory.html")
        self.assertEqual(status,200)
        self.assertIn("Regulatory",html)

    def test_unverified_demo_evaluates_without_catalogue(self):
        status,data=self.request("POST","/api/regulatory/evaluate",{
            "jurisdiction":"EU","as_of":"2026-11-08","hazards":["H315"],
            "classification_complete":{"value":"no","evidence":"Test record"},
            "facts":{"skin_contact_possible":{"value":"yes","evidence":"Synthetic input"}},
            "attributes":{},
        })
        self.assertEqual(status,200)
        self.assertEqual(data["decisions"][0]["decision"],"candidate_unverified")
        self.assertFalse(data["sds_compliance_established"])

    def test_invalid_payload_returns_400(self):
        status,data=self.request("POST","/api/regulatory/evaluate",{"jurisdiction":"EU"})
        self.assertEqual(status,400)
        self.assertIn("error",data)

if __name__=="__main__":
    unittest.main()
