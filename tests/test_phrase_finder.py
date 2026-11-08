"""Full local phrase retrieval and draft provenance checks.

Synthetic SQLite fixtures only: no licensed eSDScom text in Git.
Search ranking and curated source identity never infer legal applicability.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from catalogue_index import build_index
from phrase_finder import (PhraseFinderError,find_phrases,finder_sections,
                           validate_draft,_curated_rules)
from section_recommendations import load_candidates
from server import create_handler

DB_ROWS=[
    ("eu-eye","Core","01.04.01.04.6000.",4,"Rinse eyes thoroughly with water.","Sentence","5.5","EU",2),
    ("eu-skin","Core","01.04.01.03.18000.",4,"Wash skin with soap and plenty of water.","Sentence","5.5","EU",3),
    ("eu-fragment","Core","01.04.01.03.12000.",4,"Skin contact:","Header","5.5","EU",4),
    ("eu-parameter","Core","01.07.02.02.12000.",7,"Keep at {temperature} degrees.","Sentence","5.5","EU",5),
    ("us-eye","Core","04.04.01.04.6000.",4,"US test eye rinsing.","Sentence","5.5","US",6),
    ("eu-stability","Core","01.10.04.00.5000.",10,"Keep away from sunlight.","Sentence","5.5","EU",7),
]


def custom_pack():
    return {"rules":[
        {"id":"SYNTH_EYE","section":4,"structurecode":"01.04.01.04.6000.",
         "expected_english_sha256":hashlib.sha256(DB_ROWS[0][4].encode()).hexdigest(),
         "expected_grammar":"Sentence","subsection_hint":"4.1",
         "review_note":"Requires first-aid review"},
        {"id":"SYNTH_STAB","section":10,"structurecode":"01.10.04.00.5000.",
         "expected_english_sha256":hashlib.sha256(DB_ROWS[-1][4].encode()).hexdigest(),
         "expected_grammar":"Sentence","subsection_hint":"10.4",
         "review_note":"Requires stability evidence"},
    ]}


def snapshot(row):
    return {x:row[x] for x in ("entry_key","structurecode","sds_section",
                              "wording_hash","text_sha256","catalogue_version")}


class FinderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"phrase_catalogue.sqlite"
        self.db=sqlite3.connect(self.path)
        self.db.execute("""CREATE TABLE entries(
            entry_key TEXT PRIMARY KEY,collection TEXT,structurecode TEXT,
            sds_section INTEGER,english TEXT,grammar TEXT,revision_date_raw TEXT,
            catalogue_version TEXT,source_file TEXT,excel_row INTEGER,
            esdscom_phrase_id TEXT,original_code TEXT,region TEXT,
            jurisdiction_structure TEXT,source TEXT,info TEXT,qualifier TEXT,phrase_owner TEXT
        )""")
        for key,collection,code,section,english,grammar,version,juris,rownum in DB_ROWS:
            self.db.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key,collection,code,section,english,grammar,"",version,
                 "fake-core.xlsx",rownum,"","","",juris,"synthetic fixture","","","synthetic"))
        self.db.commit()
        build_index(self.db,source_sha256="0"*64)
    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_entire_catalogue_discovery_returns_actual_source_text(self):
        res=find_phrases(self.path,mode="catalogue",section="4")
        self.assertEqual(res["total"],3)
        self.assertEqual([r["entry_key"] for r in res["results"]],
                         ["eu-eye","eu-skin","eu-fragment"])
        self.assertEqual(res["results"][0]["english"],DB_ROWS[0][4])
        self.assertFalse(res["results"][0]["legal_applicability_verified"])
        self.assertFalse(res["results"][0]["sds_phrase_approved"])
        self.assertEqual(res["results"][0]["source_file"],"fake-core.xlsx")

    def test_subsection_and_keyword_token_filter(self):
        res=find_phrases(self.path,mode="catalogue",section="4",subsection="4.1",
                         query="rInSe WaTeR")
        self.assertEqual(res["total"],1)
        self.assertEqual(res["results"][0]["entry_key"],"eu-eye")
        self.assertEqual(find_phrases(self.path,mode="catalogue",section="7",
                                      subsection="7.2")["total"],0)

    def test_wildcards_are_literal_and_not_injection(self):
        for term in ("%", "_", "eyes' OR 1=1 --"):
            self.assertEqual(find_phrases(self.path,mode="catalogue",
                                         section="4",query=term)["total"],0)
        with self.assertRaises(PhraseFinderError):
            find_phrases(self.path,mode="catalogue",section="4",query="a "*13)

    def test_different_jurisdiction_is_not_silently_mixed(self):
        us=find_phrases(self.path,mode="catalogue",section="4",jurisdiction="US")
        self.assertEqual(us["total"],1)
        self.assertEqual(us["results"][0]["english"],"US test eye rinsing.")
        with self.assertRaises(PhraseFinderError):
            find_phrases(self.path,mode="curated",section="4",jurisdiction="GB")

    def test_curated_must_match_exact_source(self):
        result=find_phrases(self.path,section="4",subsection="4.1",pack=custom_pack())
        self.assertEqual(result["total"],1)
        x=result["results"][0]
        self.assertEqual(x["curated_rule_id"],"SYNTH_EYE")
        self.assertEqual(x["source_integrity"],"exact_source_match")
        self.assertTrue(x["selectable_for_draft"])
        self.assertFalse(x["legal_applicability_verified"])

    def test_curated_changed_wording_grammar_or_version_is_blocked(self):
        for field,value in (("english","Modified"),("grammar","Header"),
                            ("catalogue_version","5.4")):
            with self.subTest(field=field):
                original=self.db.execute(
                    f"SELECT {field} FROM entries WHERE entry_key='eu-eye'").fetchone()[0]
                self.db.execute(f"UPDATE entries SET {field}=? WHERE entry_key='eu-eye'",(value,))
                self.db.commit()
                build_index(self.db)
                r=find_phrases(self.path,section="4",pack=custom_pack())
                item=next(x for x in r["results"] if x["entry_key"]=="eu-eye")
                self.assertEqual(item["source_integrity"],"blocked_source_mismatch")
                self.assertFalse(item["selectable_for_draft"])
                self.db.execute(f"UPDATE entries SET {field}=? WHERE entry_key='eu-eye'",(original,))
                self.db.commit()
                build_index(self.db)

    def test_duplicate_curated_source_code_is_blocked(self):
        self.db.execute("INSERT INTO entries SELECT 'duplicate-eye',collection,structurecode,"
                        "sds_section,english,grammar,revision_date_raw,catalogue_version,"
                        "source_file,99,esdscom_phrase_id,original_code,region,"
                        "jurisdiction_structure,source,info,qualifier,phrase_owner "
                        "FROM entries WHERE entry_key='eu-eye'")
        self.db.commit()
        build_index(self.db)
        r=find_phrases(self.path,section="4",pack=custom_pack())
        eyes=[x for x in r["results"] if x["structurecode"]=="01.04.01.04.6000."]
        self.assertEqual(len(eyes),2)
        self.assertTrue(all(x["source_integrity"]=="blocked_source_mismatch"
                            and not x["selectable_for_draft"] for x in eyes))

    def test_flagged_placeholder_requires_opt_in_and_fragment_is_labelled(self):
        res=find_phrases(self.path,mode="catalogue",section="7")
        self.assertEqual(res["total"],0)
        res=find_phrases(self.path,mode="catalogue",section="7",include_flagged="1")
        self.assertEqual(res["total"],1)
        self.assertTrue(res["results"][0]["requires_manual_completion"])
        self.assertIn("possible_parameter_or_placeholder",res["results"][0]["source_flags"])
        pieces=find_phrases(self.path,mode="catalogue",section="4",kind="heading")
        self.assertEqual(pieces["total"],1)
        self.assertTrue(pieces["results"][0]["is_fragment"])

    def test_subsection_in_curated_uses_explicit_hint_not_catalogue_heuristic(self):
        p=custom_pack()
        self.assertEqual(list(_curated_rules(p,4,"4.1")),["01.04.01.04.6000."])
        original=load_candidates()
        self.assertTrue(_curated_rules(original,4,"4.1"))

    def test_section_counts_and_pagination(self):
        meta=finder_sections(self.path)
        self.assertEqual(len(meta["sections"]),16)
        self.assertEqual(meta["sections"][3]["total_source_phrases"],3)
        page1=find_phrases(self.path,mode="catalogue",section="4",limit=1)
        self.assertEqual(page1["total"],3)
        self.assertEqual(len(page1["results"]),1)
        page2=find_phrases(self.path,mode="catalogue",section="4",limit=1,offset=1)
        self.assertNotEqual(page1["results"][0]["entry_key"],page2["results"][0]["entry_key"])

    def test_draft_source_current_and_changes_fail_closed(self):
        item=find_phrases(self.path,mode="catalogue",section="4")["results"][0]
        data=[snapshot(item)]
        current=validate_draft(self.path,data)
        self.assertTrue(current["all_current"])
        self.assertFalse(current["reviewed_for_regulatory_applicability"])
        self.db.execute("UPDATE entries SET english='different' WHERE entry_key=?",(item["entry_key"],))
        self.db.commit()
        # Stale index is insufficient to pass: exact English hash is also checked.
        stale=validate_draft(self.path,data)
        self.assertFalse(stale["all_current"])
        self.assertEqual(stale["results"][0]["status"],"source_changed_or_missing")

    def test_reject_corrupt_draft_snapshots(self):
        item=find_phrases(self.path,mode="catalogue",section="4")["results"][0]
        record=snapshot(item)
        for invalid in ([record,record], [{**record,"text_sha256":"x"}],
                        [{**record,"extra":"error"}], [{**record,"sds_section":17}]):
            with self.subTest(data=invalid),self.assertRaises(PhraseFinderError):
                validate_draft(self.path,invalid)

    def test_invalid_filters_and_missing_database_fail_closed(self):
        for invalid in ({"section":"17"},{"subsection":"9.1"},{"mode":"unknown"},
                        {"include_flagged":"yes"},{"kind":"random"},
                        {"offset":-1},{"jurisdiction":"ALL"}):
            with self.subTest(invalid=invalid),self.assertRaises(PhraseFinderError):
                find_phrases(self.path,**invalid)
        with self.assertRaises(FileNotFoundError):
            find_phrases(self.path.with_name("missing.sqlite"),mode="catalogue",section="4")


class FinderHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),
                   create_handler(Path("/no/missing/phrase_catalogue.sqlite")))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
    def request(self,method,path,data=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            headers={"Content-Type":"application/json"} if data is not None else {}
            conn.request(method,path,body=json.dumps(data) if data is not None else None,headers=headers)
            r=conn.getresponse();value=r.read().decode()
            return r.status,(json.loads(value) if path.startswith("/api/") else value)
        finally:conn.close()
    def test_static_page(self):
        status,page=self.request("GET","/phrase_finder.html")
        self.assertEqual(status,200)
        self.assertIn("Find and",page)
    def test_missing_catalogue_returns_503(self):
        for url in ("/api/phrase-finder/sections",
                    "/api/phrase-finder/search?section=4&mode=catalogue"):
            status,out=self.request("GET",url)
            self.assertEqual(status,503)
            self.assertIn("error",out)
    def test_invalid_input_and_missing_draft_db(self):
        status,out=self.request("GET","/api/phrase-finder/search?section=99")
        self.assertEqual(status,400)
        status,out=self.request("POST","/api/phrase-finder/validate-draft",[
            {"entry_key":"bad"}])
        self.assertEqual(status,400)
        status,out=self.request("POST","/api/phrase-finder/validate-draft",[])
        self.assertEqual(status,200)
        self.assertTrue(out["all_current"])

if __name__=="__main__":
    unittest.main()
