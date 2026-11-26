"""Product profile => exact original (synthetic) SDS phrase recommendations.

Source-safe tests. No licensed eSDScom phrase text is used, fabricated or
committed. Verifies selection cues are separate from legal approval.
"""
from __future__ import annotations
import copy
import hashlib
import http.client
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from catalogue_index import build_index
from profile_phrase_engine import (
    ProfileRecommendationError, load_pack, validate_profile, recommend_profile
)
from server import create_handler

PACK, CURATED=load_pack()

def demo(**overrides):
    p={
        "jurisdiction":"EU",
        "as_of":"2026-11-08",
        "hazards":["H315","H319"],
        "product_type":"mixture",
        "physical_state":"liquid",
        "physical_form":"unknown",
        "colour":"colourless",
        "ph":5.2,
        "flash_point_c":None,
        "dust_generating":"unknown",
        "volatile":"unknown",
        "heat_sensitive":"unknown",
        "sunlight_sensitive":"unknown",
        "heat_pressure_risk":"unknown",
        "professional_use":"unknown",
        "classification_reference":"Synthetic classification reference"
    }
    p.update(overrides)
    return p

def all_candidates(result):
    return [x for s in result["sections"] for x in s["candidates"]]

def get_candidate(result,rule_id):
    return next(c for c in all_candidates(result) if c["rule_id"]==rule_id)


class ProfileEngineTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.db=Path(self.dir.name)/"catalogue.sqlite"
        self.conn=sqlite3.connect(self.db)
        self.conn.execute("""CREATE TABLE entries(
            entry_key TEXT PRIMARY KEY,collection TEXT,structurecode TEXT,
            sds_section INTEGER,english TEXT,grammar TEXT,revision_date_raw TEXT,
            catalogue_version TEXT,source_file TEXT,excel_row INTEGER,
            esdscom_phrase_id TEXT,original_code TEXT,region TEXT,
            jurisdiction_structure TEXT,source TEXT,info TEXT,qualifier TEXT,phrase_owner TEXT
        )""")
        self.ids=[
          "EXP_S02_03","EXP_S02_04","R04_SKIN_FIRST_AID",
          "R04_EYE_FIRST_AID","EXP_S09_01","R09_COLOURLESS",
          "EXP_S06_01","EXP_S08_01","EXP_S03_01",
          "R08_GLOVE_GUIDANCE","R10_AVOID_HEAT"
        ]
        self.source=copy.deepcopy({k:CURATED[k] for k in self.ids})
        self.metadata=copy.deepcopy(PACK)
        self.metadata["rules"]=[r for r in self.metadata["rules"] if r["rule_id"] in self.ids]
        self.keys={}
        for i,key in enumerate(self.ids):
            record=self.source[key]
            english="Synthetic catalogue phrase "+str(i+1)+"."
            self.keys[key]=(f"example-{i+1}",english)
            record["expected_english_sha256"]=hashlib.sha256(english.encode()).hexdigest()
            grammar=record.get("expected_grammar") or ("Header" if key=="EXP_S03_01" else "List-Element" if key.startswith("EXP_S09_") or key=="R09_COLOURLESS" else "Sentence")
            self.conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                self.keys[key][0],"Core",record["structurecode"],record["section"],
                english,grammar,"","5.5","fictional_core.xlsx",i+1,"","",
                "EU","EU","synthetic","","","synthetic"))
        self.conn.commit()
        build_index(self.conn,source_sha256="0"*64)
    def tearDown(self):
        self.conn.close()
        self.dir.cleanup()
    def evaluate(self,product=None):
        return recommend_profile(self.db,product or demo(),self.metadata,self.source)

    def test_source_rules_and_all_sections(self):
        self.assertEqual(len(PACK["rules"]),38)
        self.assertEqual(len({r["rule_id"] for r in PACK["rules"]}),38)
        self.assertTrue(all(r["rule_id"] in CURATED for r in PACK["rules"]))
        self.assertEqual(PACK["status"],"draft_phrase_relevance_not_legally_verified")
        result=self.evaluate()
        self.assertEqual(len(result["sections"]),16)
        self.assertFalse(result["sds_compliant"])
        self.assertFalse(result["classification_approved"])
        self.assertFalse(result["legal_applicability_verified"])
        self.assertFalse(result["sections_complete"])
        self.assertEqual(result["sections"][13]["section"],14)
        self.assertFalse(result["sections"][13]["candidates"])

    def test_h315_h319_liquid_colourless_produces_actual_section_text(self):
        result=self.evaluate()
        for id in ("EXP_S02_03","EXP_S02_04","R04_SKIN_FIRST_AID",
                   "R04_EYE_FIRST_AID","EXP_S09_01","R09_COLOURLESS",
                   "EXP_S08_01","EXP_S03_01"):
            with self.subTest(rule=id):
                item=get_candidate(result,id)
                self.assertEqual(item["source_integrity"],"exact_source_match")
                self.assertEqual(item["phrase"],self.keys[id][1])
                self.assertEqual(item["source"]["entry_key"],self.keys[id][0])
                self.assertFalse(item["approved_for_sds"])
                self.assertFalse(item["legal_applicability_verified"])
                self.assertTrue(item["confirmation_required"])
        self.assertEqual(get_candidate(result,"EXP_S09_01")["kind"],"reported_property")
        self.assertTrue(get_candidate(result,"EXP_S09_01")["is_fragment"])
        self.assertGreater(result["total_recommended_source_phrases"],5)

    def test_p_h_screening_only_never_calculates_a_classification(self):
        result=self.evaluate(demo(hazards=[],physical_state="unknown",colour="unknown",
                                  product_type="unknown",ph=1.5))
        self.assertEqual(set(x["rule_id"] for x in all_candidates(result)),
                         {"EXP_S08_01","R08_GLOVE_GUIDANCE"})
        self.assertEqual(result["hazards"],[])
        self.assertFalse(result["classification_approved"])
        middle=self.evaluate(demo(hazards=[],physical_state="unknown",colour="unknown",
                                  product_type="unknown",ph=7.0))
        self.assertFalse(all_candidates(middle))

    def test_flashpoint_is_screening_not_clp_assignment(self):
        low=self.evaluate(demo(hazards=[],physical_state="liquid",
            product_type="unknown",colour="unknown",ph=None,flash_point_c=25))
        self.assertEqual(get_candidate(low,"EXP_S06_01")["kind"],"conditional_safety")
        self.assertEqual(low["hazards"],[])
        cutoff=self.evaluate(demo(hazards=[],physical_state="liquid",
            product_type="unknown",colour="unknown",ph=None,flash_point_c=60))
        self.assertNotIn("EXP_S06_01",{c["rule_id"] for c in all_candidates(cutoff)})

    def test_logical_physical_hazard_conflicts_block_all_recommendations(self):
        profiles=[
            demo(hazards=["H225"],physical_state="solid"),
            demo(hazards=["H220"],physical_state="liquid"),
            demo(hazards=["H228"],physical_state="gas"),
            demo(hazards=["H318","H319"]),
            demo(hazards=[],physical_state="liquid",physical_form="powder"),
        ]
        for value in profiles:
            with self.subTest(profile=value):
                result=self.evaluate(value)
                self.assertTrue(result["blocked_due_to_profile_conflict"])
                self.assertTrue(result["profile_conflicts"])
                self.assertFalse(all_candidates(result))
                self.assertEqual(len(result["sections"]),16)

    def test_unknown_profile_does_not_infer_negative_statements(self):
        minimal={"jurisdiction":"EU","as_of":"2026-11-08","hazards":[]}
        result=recommend_profile(Path(self.dir.name)/"missing.sqlite",minimal,
                                 self.metadata,self.source)
        self.assertEqual(result["total_recommended_source_phrases"],0)
        self.assertFalse(all_candidates(result))
        self.assertTrue(all(not s["section_complete"] for s in result["sections"]))

    def test_no_transport_or_nonhazardous_claim_in_profile_pack(self):
        for item in PACK["rules"]:
            self.assertNotIn(CURATED[item["rule_id"]]["section"],{11,12,13,14,15,16})
        self.assertNotIn("R14_NOT_DANGEROUS_GOODS",[r["rule_id"] for r in PACK["rules"]])
        self.assertNotIn("EXP_S02_01",[r["rule_id"] for r in PACK["rules"]])

    def test_source_wording_change_fails_closed(self):
        key,old=self.keys["R04_EYE_FIRST_AID"]
        self.conn.execute("UPDATE entries SET english='Changed text' WHERE entry_key=?",(key,))
        self.conn.commit()
        # Source SHA is checked even when index is stale.
        result=self.evaluate()
        got=get_candidate(result,"R04_EYE_FIRST_AID")
        self.assertEqual(got["source_integrity"],"blocked_catalogue_mismatch")
        self.assertIsNone(got["phrase"])
        self.assertIsNone(got["source"])

    def test_duplicate_source_code_fails_closed(self):
        key,_=self.keys["EXP_S09_01"]
        self.conn.execute(
            """INSERT INTO entries
               SELECT 'duplicate-phrase',collection,structurecode,sds_section,english,
               grammar,revision_date_raw,catalogue_version,source_file,999,
               esdscom_phrase_id,original_code,region,jurisdiction_structure,
               source,info,qualifier,phrase_owner
               FROM entries WHERE entry_key=?""",(key,))
        self.conn.commit()
        got=get_candidate(self.evaluate(),"EXP_S09_01")
        self.assertEqual(got["source_integrity"],"blocked_catalogue_mismatch")
        self.assertIsNone(got["phrase"])

    def test_mismatched_grammar_fails_closed(self):
        key,_=self.keys["EXP_S02_03"]
        self.conn.execute("UPDATE entries SET grammar='List-Element' WHERE entry_key=?",(key,))
        self.conn.commit()
        got=get_candidate(self.evaluate(),"EXP_S02_03")
        self.assertEqual(got["source_integrity"],"blocked_catalogue_mismatch")

    def test_flagged_parameter_source_fails_closed_even_with_valid_hash(self):
        key,_=self.keys["EXP_S08_01"]
        replacement="Fictional {parameter} goggles instruction."
        self.source["EXP_S08_01"]["expected_english_sha256"]=hashlib.sha256(replacement.encode()).hexdigest()
        self.conn.execute("UPDATE entries SET english=? WHERE entry_key=?",(replacement,key))
        self.conn.commit()
        build_index(self.conn)
        got=get_candidate(self.evaluate(),"EXP_S08_01")
        self.assertEqual(got["source_integrity"],"blocked_catalogue_mismatch")

    def test_hazard_only_no_database_returns_unavailable(self):
        with self.assertRaises(FileNotFoundError):
            recommend_profile(Path(self.dir.name)/"missing.sqlite",demo(),
                              self.metadata,self.source)

    def test_validation_rejects_invalid_products(self):
        tests=[
          demo(jurisdiction="US"),demo(as_of="2026-02-30"),demo(hazards=["HXYZ"]),
          demo(hazards=["H315","H315"]),demo(ph=30),demo(ph=True),
          demo(flash_point_c="25"),demo(physical_state="plasma"),
          demo(physical_form="powder",extraneous="bad"),
          demo(classification_reference="A"*401),
        ]
        for data in tests:
            with self.subTest(profile=data),self.assertRaises(ProfileRecommendationError):
                validate_profile(data)


class ProfileHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),
            create_handler(Path("/no/installed/catalogue.sqlite")))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
    def call(self,method,path,data=None):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            body=json.dumps(data) if data is not None else None
            headers={"Content-Type":"application/json"} if data is not None else {}
            c.request(method,path,body=body,headers=headers)
            r=c.getresponse();txt=r.read().decode("utf8")
            return r.status,json.loads(txt) if path.startswith("/api/") else txt
        finally:c.close()
    def test_profile_browser_serves(self):
        status,html=self.call("GET","/profile_recommendations.html")
        self.assertEqual(status,200)
        self.assertIn("suggested phrases",html)
    def test_invalid_json_profile_returns_400(self):
        status,data=self.call("POST","/api/profile-recommendations/evaluate",
                              {"jurisdiction":"EU","as_of":"2026-01-01","hazards":["invalid"]})
        self.assertEqual(status,400)
        self.assertIn("error",data)
    def test_no_source_fallback_on_missing_local_catalogue(self):
        status,data=self.call("POST","/api/profile-recommendations/evaluate",demo())
        self.assertEqual(status,503)
        self.assertIn("error",data)
    def test_blank_profile_can_return_empty_all_sections(self):
        status,data=self.call("POST","/api/profile-recommendations/evaluate",
            {"jurisdiction":"EU","as_of":"2026-11-08","hazards":[]})
        self.assertEqual(status,200)
        self.assertEqual(len(data["sections"]),16)
        self.assertEqual(data["total_recommended_source_phrases"],0)
        self.assertFalse(data["sds_compliant"])

if __name__=="__main__":
    unittest.main()
