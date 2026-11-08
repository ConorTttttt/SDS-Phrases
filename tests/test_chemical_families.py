"""Source-safe tests: user-selected chemical families produce actual source phrase candidates.

All catalogue text here is deliberately fictional and only synthetic test
fixtures are committed. Actual eSDScom 5.5 source text is read locally.
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
from chemical_families import (
    ChemicalFamilyError, family_candidates, load_family_pack,
    public_families, validate_family_inputs,
)
from profile_phrase_engine import (
    ProfileRecommendationError, recommend_profile, validate_profile,
)
from server import create_handler

REAL_PACK=load_family_pack()


def product(**changes):
    data={
        "jurisdiction":"EU","as_of":"2026-11-08","hazards":[],
        "product_type":"unknown","physical_state":"unknown",
        "physical_form":"unknown","colour":"unknown",
        "chemical_families":[],"family_assessments":{},
    }
    data.update(changes)
    return data


class FamilyPackTests(unittest.TestCase):
    def test_source_mapping_scope_and_provenance(self):
        self.assertEqual(len(REAL_PACK["families"]),10)
        self.assertEqual(len(REAL_PACK["rules"]),23)
        self.assertEqual(len({r["id"] for r in REAL_PACK["rules"]}),23)
        self.assertEqual({r["family"] for r in REAL_PACK["rules"]},
                         {r["id"] for r in REAL_PACK["families"]})
        self.assertTrue(all(len(r["expected_english_sha256"])==64 for r in REAL_PACK["rules"]))
        self.assertTrue(all("english" not in r for r in REAL_PACK["rules"]))
        self.assertTrue(all(r["legal_status"]=="not_verified" for r in REAL_PACK["rules"]))
        self.assertTrue(all(r["review_status"]=="human_applicability_review_required"
                            for r in REAL_PACK["rules"]))
        self.assertTrue(all(r["expected_grammar"] in ("Sentence","List-Element")
                            for r in REAL_PACK["rules"]))

    def test_pack_summary_does_not_redistribute_licensed_phrases(self):
        summary=public_families()
        self.assertEqual(len(summary["families"]),10)
        self.assertEqual(summary["rule_count"],23)
        self.assertEqual(summary["jurisdiction"],"EU")
        self.assertNotIn("structurecode",json.dumps(summary))
        self.assertNotIn("expected_english_sha256",json.dumps(summary))

    def test_invalid_family_and_process_choices_fail(self):
        cases=[
            (["unknown"],{}),
            (["acids","acids"],{}),
            ("acids",{}),
            (["acids"],{"unrecognised":"yes"}),
            (["acids"],{"water_dilution_approved":"approved"}),
            (["acids"],[]),
        ]
        for families,assessment in cases:
            with self.subTest(families=families,assessment=assessment):
                with self.assertRaises(ChemicalFamilyError):
                    validate_family_inputs(families,assessment,REAL_PACK)

    def test_profile_api_rejects_unknown_chemical_family(self):
        for bad in (
            product(chemical_families=["never_known"]),
            product(chemical_families=["acids","acids"]),
            product(family_assessments={"water_dilution_approved":True}),
        ):
            with self.subTest(profile=bad),self.assertRaises(ProfileRecommendationError):
                validate_profile(bad)


class FamilySourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/"family.sqlite"
        self.conn=sqlite3.connect(self.db)
        self.conn.execute("""CREATE TABLE entries(
            entry_key TEXT PRIMARY KEY,collection TEXT,structurecode TEXT,
            sds_section INTEGER,english TEXT,grammar TEXT,revision_date_raw TEXT,
            catalogue_version TEXT,source_file TEXT,excel_row INTEGER,
            esdscom_phrase_id TEXT,original_code TEXT,region TEXT,
            jurisdiction_structure TEXT,source TEXT,info TEXT,qualifier TEXT,phrase_owner TEXT
        )""")
        self.pack=copy.deepcopy(REAL_PACK)
        # Include the full ten-family taxonomy but use a compact, fictional
        # source subset to exercise every important gating operation.
        selected={
          ("acids","7.2"),("acids","7.1"),
          ("alkalis","7.2"),
          ("organic_solvents","7.2"),
          ("isocyanates","2.2"),
          ("epoxy_resins","2.2"),
          ("oxidising_substances","10.4"),
          ("organic_peroxides","10.4"),
          ("water_reactive_substances","6.3"),
          ("metal_powders","6.1"),
          ("acid_reactive_gas_releasers","2.2"),
        }
        filtered=[]
        found=set()
        for row in self.pack["rules"]:
            key=(row["family"],row["subsection"])
            if key not in selected:
                if row["assessment"] if "assessment" in row else False:
                    filtered.append(row)
                continue
            if key in found and row["family"] not in ("isocyanates","acid_reactive_gas_releasers","water_reactive_substances","acids"):
                continue
            filtered.append(row);found.add(key)
        self.pack["rules"]=filtered
        self.records={}
        by_code={}
        for n,row in enumerate(filtered):
            code=row["structurecode"]
            if code in by_code:
                row["expected_english_sha256"]=by_code[code]["sha"]
                continue
            text="Fictional source phrase "+str(n+1)+"."
            sha=hashlib.sha256(text.encode()).hexdigest()
            row["expected_english_sha256"]=sha
            by_code[code]={"text":text,"sha":sha}
            key="family-test-"+str(n+1)
            self.records[code]=(key,text)
            self.conn.execute("INSERT INTO entries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                key,"Core",code,row["section"],text,row["expected_grammar"],
                "","5.5","fictional_family.xlsx",n+1,"","","EU","EU",
                "synthetic","","","synthetic"
            ))
        self.conn.commit()
        build_index(self.conn,source_sha256="0"*64)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    def recs(self,p):
        return family_candidates(self.db,p,pack=self.pack)

    def test_no_families_no_source_fetch(self):
        self.assertEqual(family_candidates(self.db.with_name("missing.db"),
                                          product(),pack=self.pack),[])

    def test_family_without_hazard_retrieves_actual_catalogue_wording(self):
        result=self.recs(product(chemical_families=["acids"]))
        self.assertGreaterEqual(len(result),2)
        self.assertTrue(all(x["section"]==7 for x in result))
        self.assertTrue(all(x["source_integrity"]=="exact_source_match" for x in result))
        for got in result:
            self.assertEqual(got["phrase"],self.records[got["source"]["structurecode"]][1])
            self.assertFalse(got["legal_applicability_verified"])
            self.assertFalse(got["approved_for_sds"])
            self.assertIn("acids",got["family_ids"])
            self.assertTrue(got["confirmation_required"])

    def test_isocyanates_and_epoxy_are_label_candidates_not_approved(self):
        result=self.recs(product(chemical_families=["isocyanates","epoxy_resins"]))
        self.assertEqual(len(result),3)
        self.assertTrue(all(x["section"]==2 for x in result))
        self.assertEqual(sum(x["kind"]=="family_label_review" for x in result),2)
        self.assertEqual(sum(x["kind"]=="family_safety_review" for x in result),1)
        self.assertTrue(all(x["phrase"] for x in result))
        self.assertTrue(all(x["approved_for_sds"] is False for x in result))

    def test_h260_gate_applies_to_water_reactive_phrases(self):
        base=product(chemical_families=["water_reactive_substances"])
        self.assertFalse(self.recs(base))
        hit=self.recs({**base,"hazards":["H260"]})
        self.assertGreaterEqual(len(hit),1)
        self.assertTrue(all("entered classification: H260" in x["matched_inputs"] for x in hit))
        self.assertFalse(self.recs({**base,"hazards":["H315"]}))

    def test_only_correct_euh_code_triggers_correct_acid_contact_warning(self):
        base=product(chemical_families=["acid_reactive_gas_releasers"])
        self.assertFalse(self.recs(base))
        result=self.recs({**base,"hazards":["EUH031"]})
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["topic"],"EUH031 supplemental label wording")
        self.assertFalse(result[0]["approved_for_sds"])
        result2=self.recs({**base,"hazards":["EUH032"]})
        self.assertEqual(len(result2),1)
        self.assertEqual(result2[0]["topic"],"EUH032 supplemental label wording")

    def test_oxidiser_and_peroxide_share_original_source_without_duplicate(self):
        base=product(chemical_families=["oxidising_substances","organic_peroxides"])
        self.assertEqual(self.recs(base),[])
        result=self.recs({**base,"hazards":["H272","H242"]})
        self.assertEqual(len(result),1)
        self.assertEqual(set(result[0]["family_ids"]),
                         {"oxidising_substances","organic_peroxides"})
        self.assertEqual(result[0]["source_integrity"],"exact_source_match")

    def test_metal_powders_need_solid_form_and_powder_or_dust(self):
        base=product(chemical_families=["metal_powders"])
        self.assertEqual(self.recs(base),[])
        state={**base,"physical_state":"solid"}
        self.assertEqual(self.recs(state),[])
        result=self.recs({**state,"physical_form":"powder"})
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["section"],6)
        self.assertFalse(self.recs({**base,"physical_state":"liquid",
                                     "physical_form":"powder"}))

    def test_process_specific_dilution_needs_explicit_assessment(self):
        base=product(chemical_families=["acids"])
        unknown=self.recs(base)
        self.assertNotIn("Water dilution procedure",{r["topic"] for r in unknown})
        accepted=self.recs({**base,"family_assessments":{"water_dilution_approved":"yes"}})
        self.assertIn("Water dilution procedure",{r["topic"] for r in accepted})
        self.assertTrue(all(not r["approved_for_sds"] for r in accepted))

    def test_source_text_mutation_blocks_original_wording(self):
        source=self.recs(product(chemical_families=["alkalis"]))[0]
        key=source["source"]["entry_key"]
        self.conn.execute("UPDATE entries SET english='changed' WHERE entry_key=?",(key,))
        self.conn.commit()
        # An outdated catalogue_index cannot cause a silent false match.
        changed=self.recs(product(chemical_families=["alkalis"]))[0]
        self.assertEqual(changed["source_integrity"],"blocked_catalogue_mismatch")
        self.assertIsNone(changed["phrase"])
        self.assertIsNone(changed["source"])

    def test_duplicate_source_code_fails_closed(self):
        source=self.recs(product(chemical_families=["alkalis"]))[0]
        key=source["source"]["entry_key"]
        self.conn.execute("""INSERT INTO entries
            SELECT 'duplicated-family',collection,structurecode,sds_section,english,
                grammar,revision_date_raw,catalogue_version,source_file,999,
                esdscom_phrase_id,original_code,region,jurisdiction_structure,
                source,info,qualifier,phrase_owner FROM entries WHERE entry_key=?""",(key,))
        self.conn.commit()
        result=self.recs(product(chemical_families=["alkalis"]))
        self.assertTrue(all(x["source_integrity"]=="blocked_catalogue_mismatch" for x in result))

    def test_changed_grammar_blocks_family_source(self):
        original=self.recs(product(chemical_families=["epoxy_resins"]))[0]
        key=original["source"]["entry_key"]
        self.conn.execute("UPDATE entries SET grammar='Header' WHERE entry_key=?",(key,))
        self.conn.commit()
        got=self.recs(product(chemical_families=["epoxy_resins"]))[0]
        self.assertEqual(got["source_integrity"],"blocked_catalogue_mismatch")

    def test_profile_section_integration_with_family_only(self):
        # Exclude base pilot mappings by supplying an empty profile pack.
        core={"schema":"sds-phrase-profile-recommendations/v0.1","rules":[]}
        product_data=product(chemical_families=["epoxy_resins"])
        result=recommend_profile(self.db,product_data,pack=core,source_pack={},
                                 family_pack=self.pack)
        self.assertEqual(len(result["sections"]),16)
        self.assertEqual(result["total_recommended_source_phrases"],1)
        self.assertFalse(result["sds_compliant"])
        got=result["sections"][1]["candidates"][0]
        self.assertEqual(got["kind"],"family_label_review")
        self.assertIn("epoxy_resins",got["family_ids"])

    def test_family_water_reactive_and_water_dilution_conflict(self):
        core={"schema":"sds-phrase-profile-recommendations/v0.1","rules":[]}
        result=recommend_profile(self.db,product(
            chemical_families=["water_reactive_substances"],
            family_assessments={"water_dilution_approved":"yes"},
            hazards=["H260"]),pack=core,source_pack={},family_pack=self.pack)
        self.assertTrue(result["blocked_due_to_profile_conflict"])
        self.assertEqual(result["total_recommended_source_phrases"],0)


class FamilyAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),
            create_handler(Path("/no/local/catalogue.sqlite")))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
    def request(self,method,path,data=None):
        c=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        try:
            body=json.dumps(data) if data is not None else None
            headers={"Content-Type":"application/json"} if body else {}
            c.request(method,path,body=body,headers=headers)
            response=c.getresponse();text=response.read().decode()
            return response.status,json.loads(text)
        finally:
            c.close()
    def test_public_family_choices(self):
        status,config=self.request("GET","/api/profile-recommendations/families")
        self.assertEqual(status,200)
        self.assertEqual(len(config["families"]),10)
    def test_invalid_family_400_and_missing_local_source_503(self):
        status,data=self.request("POST","/api/profile-recommendations/evaluate",
                                product(chemical_families=["nonexistent"]))
        self.assertEqual(status,400)
        self.assertIn("error",data)
        status,data=self.request("POST","/api/profile-recommendations/evaluate",
                                product(chemical_families=["epoxy_resins"]))
        self.assertEqual(status,503)
        self.assertIn("error",data)

if __name__=="__main__":
    unittest.main()
