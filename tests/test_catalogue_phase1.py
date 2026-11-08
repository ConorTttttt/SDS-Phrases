"""Phase 1 metadata tests; synthetic records only."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from catalogue_index import build_index,revision_date
from catalogue_browser import search,summary,CatalogueQueryError
from catalogue_reviews import lookup,set_review,ReviewError

class CataloguePhase1Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"catalogue.sqlite"
        self.reviews=Path(self.temp.name)/"catalogue_reviews.sqlite"
        self.conn=sqlite3.connect(self.path)
        self.conn.execute("""CREATE TABLE entries (
            entry_key TEXT PRIMARY KEY,collection TEXT,structurecode TEXT,
            sds_section INTEGER,english TEXT,grammar TEXT,revision_date_raw TEXT,
            catalogue_version TEXT,source_file TEXT,excel_row INTEGER,
            esdscom_phrase_id TEXT,original_code TEXT,region TEXT,
            jurisdiction_structure TEXT,source TEXT,info TEXT,qualifier TEXT,phrase_owner TEXT
        )""")
        self.conn.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",[
           ("a","Core","01.04.01.03.18000.",4,"Wash with water.","Sentence","44530","5.5","core.xlsx",2,"","","EU","EU","","","","eSDScom"),
           ("b","Core","02.04.01.03.18000.",4,"Wash with water.","Sentence","44530","5.5","core.xlsx",3,"","","GB","GB","","","","eSDScom"),
           ("c","Core","01.09.01.1000.",9,"Use {parameter}.","Sentence","44530","5.5","core.xlsx",4,"","","EU","EU","","","","eSDScom"),
           ("d","Core","11.01.1001.",None,"°C","List-Element","","5.5","core.xlsx",5,"","","EU","","","","","eSDScom"),
           ("e","ExpoScenario","09.01.01.",None,"Scenario heading","Header","","5.5","expo.xlsx",2,"4242","","EU","","","","","eSDScom"),
           ("f","Core","01.02.99.1000.",2,"","Header","","5.5","core.xlsx",6,"","","EU","EU","","","","eSDScom"),
        ])
        self.conn.commit()
        self.index=build_index(self.conn,source_sha256="a"*64)
    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def test_sds_subsection_special_and_flags(self):
        rows=search(self.path,jurisdiction="ALL",collection="ALL",limit=20)["results"]
        data={row["entry_key"]:row for row in rows}
        self.assertEqual(data["a"]["sds_subsection"],"4.1")
        self.assertEqual(data["a"]["sds_topic"],"First-aid description")
        self.assertEqual(data["a"]["duplicate_count"],2)
        self.assertEqual(data["a"]["duplicate_contexts"],2)
        self.assertEqual(data["d"]["sds_subsection"],"")
        self.assertIn("non_sds_structure",data["d"]["quality_flags"])
        self.assertIn("non_sds_structure",data["e"]["quality_flags"])
        self.assertIn("unmapped_catalogue_subsection",data["f"]["quality_flags"])
        self.assertIn("missing_english",data["f"]["quality_flags"])
        self.assertIn("possible_parameter_or_placeholder",data["c"]["quality_flags"])

    def test_search_and_summary(self):
        r=search(self.path,jurisdiction="EU",subsection="4.1",query="WASH")
        self.assertEqual(r["total"],1)
        self.assertEqual(r["results"][0]["entry_key"],"a")
        self.assertEqual(search(self.path,jurisdiction="ALL",collection="ALL",duplicates="repeated")["total"],2)
        self.assertEqual(search(self.path,jurisdiction="ALL",collection="ALL",quality="flagged")["total"],4)
        self.assertEqual(summary(self.path)["records"],6)
        self.assertEqual(summary(self.path)["wording_groups"],4)
        self.assertEqual(summary(self.path)["source_archive_sha256"],"a"*64)

    def test_bad_filters(self):
        for bad in ({"jurisdiction":"ZZ"},{"subsection":"4.1 OR 1=1"},
                    {"limit":-1},{"duplicates":"bogus"},{"section":"5","subsection":"4.1"}):
            with self.subTest(bad=bad),self.assertRaises(CatalogueQueryError):
                search(self.path,**bad)

    def test_catalogue_revision_not_legal_date(self):
        self.assertEqual(revision_date("44530"),"2021-11-30")
        self.assertEqual(revision_date("20231131"),"")
        self.assertEqual(self.index["indexed_rows"],6)

    def test_reviews_survive_reindex_and_stale_on_wording_change(self):
        row=search(self.path,jurisdiction="EU",section="4")["results"][0]
        set_review(self.path,self.reviews,entry_key=row["entry_key"],wording_hash=row["wording_hash"],
                   status="metadata_checked",note="Checked source field")
        lookup(self.reviews,[row])
        self.assertEqual(row["review_status"],"metadata_checked")
        self.conn.execute("UPDATE entries SET english='Different wording' WHERE entry_key='a'")
        self.conn.commit()
        build_index(self.conn)
        changed=search(self.path,jurisdiction="EU",section="4")["results"][0]
        lookup(self.reviews,[changed])
        self.assertTrue(changed["review_stale"])
        self.assertEqual(changed["review_status"],"unreviewed")
        self.assertEqual(summary(self.path)["source_archive_sha256"],"a"*64)

    def test_unauthorised_regulatory_approval_not_a_review_status(self):
        with self.assertRaises(ReviewError):
            set_review(self.path,self.reviews,entry_key="a",wording_hash="0"*64,status="legally_approved")
        with self.assertRaises(ReviewError):
            set_review(self.path,self.reviews,entry_key="a",wording_hash="0"*64,status="metadata_checked")

if __name__=="__main__":
    unittest.main()
