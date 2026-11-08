"""Section phrase recommendations: synthetic fixture, no copyrighted phrase catalogue.

Tests verify evidence gating, all-section output, exact source hashes,
non-legal status, conflicts and API behaviour.
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
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from section_recommendations import (
    RecommendationError,
    evaluate_sections,
    load_candidates,
    validate_candidates,
)
from server import create_handler

STRUCTURE = json.loads((ROOT / "rules" / "eu_reach_annex2_partb_2026.json").read_text(encoding="utf-8"))
PACK = load_candidates()


def fact(value="yes", evidence="Synthetic test document"):
    return {"value": value, "evidence": evidence}


def profile(**kwargs):
    data = {
        "jurisdiction": "EU", "as_of": "2026-11-08",
        "hazards": ["H315", "H319"],
        "classification_complete": fact(),
        "facts": {},
        "attributes": {"product_type": {"value": "mixture", "evidence": "Synthetic specification"}},
    }
    data.update(kwargs)
    return data


def rule(result, id):
    return next(x for sec in result["sections"] for x in sec["recommendations"] if x["rule_id"] == id)


class SectionRecommendationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "catalogue.sqlite"
        self.pack = copy.deepcopy(PACK)
        self.test_wording = "Fictional, locally verified draft wording."
        self.target = next(x for x in self.pack["rules"] if x["id"] == "R07_SEALED_STORAGE")
        self.target["expected_english_sha256"] = hashlib.sha256(self.test_wording.encode()).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def install_fake_catalogue(self, *, wrong_text=False, wrong_version=False, wrong_section=False, duplicate=False):
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""CREATE TABLE entries (
                entry_key TEXT UNIQUE, catalogue_version TEXT, collection TEXT, source_file TEXT,
                excel_row INTEGER, structurecode TEXT, esdscom_phrase_id TEXT, original_code TEXT,
                english TEXT, sds_section INTEGER, region TEXT, phrase_owner TEXT, source TEXT,
                info TEXT, grammar TEXT
            );""")
            base = (
                "fake-v55-core-r1", "5.6" if wrong_version else "5.5", "Core",
                "fictional.xlsx", 24, self.target["structurecode"], "", "",
                "Changed wording" if wrong_text else self.test_wording,
                6 if wrong_section else 7, "EU", "synthetic", "test fixture", "", "Sentence"
            )
            conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", base)
            if duplicate:
                conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    "fake-v55-core-r2", *base[1:]))

    def test_all_sections_have_at_least_one_curated_candidate(self):
        self.assertEqual(len(PACK["rules"]), 105)
        self.assertEqual({rule["section"] for rule in PACK["rules"]}, set(range(1, 17)))
        out = evaluate_sections(self.db, profile(), pack=PACK, structure=STRUCTURE)
        self.assertEqual(len(out["sections"]), 16)
        self.assertFalse(out["catalogue_installed"])
        self.assertFalse(out["sds_compliant"])
        self.assertFalse(out["phrases_approved"])
        self.assertTrue(all(not s["complete"] for s in out["sections"]))
        self.assertEqual(out["counts"]["draft_candidate"], 0)

    def test_known_fact_recommends_exact_source_wording_with_review_flag(self):
        self.install_fake_catalogue()
        out = evaluate_sections(self.db, profile(
            facts={"tightly_closed_storage_confirmed_safe": fact()}),
            pack=self.pack, structure=STRUCTURE)
        got = rule(out, "R07_SEALED_STORAGE")
        self.assertEqual(got["decision"], "draft_candidate")
        self.assertEqual(got["phrase"], self.test_wording)
        self.assertEqual(got["source"]["entry_key"], "fake-v55-core-r1")
        self.assertEqual(got["source"]["structurecode"], self.target["structurecode"])
        self.assertFalse(got["legally_required"])
        self.assertFalse(got["approved_for_sds"])
        self.assertEqual(out["counts"]["draft_candidate"], 1)

    def test_no_evidence_is_not_a_recommendation(self):
        self.install_fake_catalogue()
        for value, text in (("unknown", ""), ("yes", "")):
            with self.subTest(value=value):
                out = evaluate_sections(self.db, profile(
                    facts={"tightly_closed_storage_confirmed_safe": fact(value, text)}),
                    pack=self.pack, structure=STRUCTURE)
                got = rule(out, "R07_SEALED_STORAGE")
                self.assertEqual(got["decision"], "evidence_required")
                self.assertIn("facts.tightly_closed_storage_confirmed_safe", got["missing_information"])
                self.assertIsNone(got["phrase"])

    def test_evidenced_no_does_not_select_phrase(self):
        self.install_fake_catalogue()
        out = evaluate_sections(self.db, profile(
            facts={"tightly_closed_storage_confirmed_safe": fact("no")}),
            pack=self.pack, structure=STRUCTURE)
        self.assertEqual(rule(out, "R07_SEALED_STORAGE")["decision"], "not_triggered")

    def test_mismatched_or_duplicate_catalogue_fail_closed(self):
        for changes in ({"wrong_text": True}, {"wrong_section": True},
                        {"wrong_version": True}, {"duplicate": True}):
            with self.subTest(changes=changes):
                if self.db.exists():self.db.unlink()
                self.install_fake_catalogue(**changes)
                out = evaluate_sections(self.db, profile(
                    facts={"tightly_closed_storage_confirmed_safe": fact()}),
                    pack=self.pack, structure=STRUCTURE)
                got = rule(out, "R07_SEALED_STORAGE")
                self.assertEqual(got["decision"], "blocked_catalogue_mismatch")
                self.assertIsNone(got["phrase"])

    def test_missing_catalogue_with_positive_fact_is_blocked(self):
        got = rule(evaluate_sections(self.db, profile(
            facts={"tightly_closed_storage_confirmed_safe": fact()}),
            pack=self.pack, structure=STRUCTURE), "R07_SEALED_STORAGE")
        self.assertEqual(got["decision"], "blocked_catalogue_mismatch")
        self.assertIsNone(got["source"])

    def test_hazard_requirements_match_yes_absent_unknown_and_absent_complete(self):
        p = profile(facts={"soap_water_skin_first_aid_assessed": fact()})
        first = rule(evaluate_sections(self.db, p, pack=PACK, structure=STRUCTURE), "R04_SKIN_FIRST_AID")
        self.assertEqual(first["decision"], "blocked_catalogue_mismatch")
        self.assertIn("H315", first["matched_hazards"])
        p["hazards"] = ["H319"]
        p["classification_complete"] = fact("unknown", "")
        undecided = rule(evaluate_sections(self.db, p, pack=PACK, structure=STRUCTURE), "R04_SKIN_FIRST_AID")
        self.assertEqual(undecided["decision"], "evidence_required")
        self.assertIn("classification_complete", undecided["missing_information"])
        p["classification_complete"] = fact("yes", "Confirmed complete synthetic classification")
        negative = rule(evaluate_sections(self.db, p, pack=PACK, structure=STRUCTURE), "R04_SKIN_FIRST_AID")
        self.assertEqual(negative["decision"], "not_triggered")

    def test_uncertain_product_type_prevents_mixture_or_substance_claims(self):
        data = profile(facts={"ionic_mixture_identity_confirmed": fact()},
                       attributes={"product_type": {"value": "mixture", "evidence": ""}})
        out = evaluate_sections(self.db, data, pack=PACK, structure=STRUCTURE)
        got = rule(out, "R03_IONIC_MIXTURE")
        self.assertEqual(got["decision"], "evidence_required")
        self.assertIn("attributes.product_type", got["missing_information"])

    def test_conflicting_csa_facts_block_both_options(self):
        data = profile(
            attributes={"product_type": {"value": "substance", "evidence": "Reviewed identity"}},
            facts={"substance_csa_performed_verified": fact(), "substance_csa_not_performed_verified": fact()})
        out = evaluate_sections(self.db, data, pack=PACK, structure=STRUCTURE)
        self.assertEqual(rule(out, "R15_CSA_CARRIED_OUT")["decision"], "blocked_conflicting_evidence")
        self.assertEqual(rule(out, "R15_CSA_NOT_CARRIED_OUT")["decision"], "blocked_conflicting_evidence")

    def test_foreign_jurisdiction_not_mapped_to_eu(self):
        out = evaluate_sections(self.db, profile(jurisdiction="GB"), pack=PACK, structure=STRUCTURE)
        self.assertTrue(all(x["decision"] == "outside_jurisdiction"
                            for s in out["sections"] for x in s["recommendations"]))

    def test_84_additional_rules_are_scoped_and_source_hash_pinned(self):
        expanded = [x for x in PACK["rules"] if x["id"].startswith("EXP_")]
        self.assertEqual(len(expanded), 84)
        self.assertEqual({x["section"] for x in expanded}, set(range(1, 17)))
        self.assertTrue(all(x.get("expected_grammar") in ("Sentence", "Header", "List-Start", "List-Element") for x in expanded))
        self.assertTrue(all(x.get("subsection_hint") for x in expanded))
        self.assertTrue(all(x.get("source_review") == "english_sha256_checked_against_user_supplied_original_5_5_sqlite" for x in expanded))

    def test_clp_unclassified_mixture_cannot_conflict_with_hazard_codes(self):
        data = profile(facts={
            "mixture_not_classified_under_clp_reviewed": fact(),
            "classification_assessment_approved": fact(),
        })
        result = evaluate_sections(self.db, data, pack=PACK, structure=STRUCTURE)
        self.assertEqual(rule(result, "EXP_S02_01")["decision"], "blocked_conflicting_evidence")
        self.assertFalse(result["sds_compliant"])

    def test_clp_hazardous_vs_nonhazardous_assertions_block_both(self):
        data = profile(hazards=[],facts={
            "mixture_not_classified_under_clp_reviewed": fact(),
            "eu_clp_hazardous_mixture_confirmed": fact(),
            "classification_assessment_approved": fact(),
        })
        result = evaluate_sections(self.db, data, pack=PACK, structure=STRUCTURE)
        self.assertEqual(rule(result, "EXP_S02_01")["decision"], "blocked_conflicting_evidence")
        self.assertEqual(rule(result, "R02_CLP_HAZARDOUS_MIXTURE")["decision"], "blocked_conflicting_evidence")

    def test_multiple_conflicting_physical_states_block_all_physical_state_candidates(self):
        data = profile(
            attributes={
                "product_type": {"value":"mixture","evidence":"Synthetic product"},
                "physical_form": {"value":"liquid","evidence":"Synthetic physical data"}
            },
            facts={
                "physical_state_liquid_verified": fact(),
                "physical_state_solid_verified": fact(),
            })
        result = evaluate_sections(self.db, data, pack=PACK, structure=STRUCTURE)
        self.assertEqual(rule(result, "EXP_S09_01")["decision"], "blocked_conflicting_evidence")
        self.assertEqual(rule(result, "EXP_S09_02")["decision"], "blocked_conflicting_evidence")

    def test_noncombustibility_claim_conflicts_with_flammability_hazard(self):
        data = profile(hazards=["H225"],facts={"product_non_combustible_confirmed": fact()})
        result = evaluate_sections(self.db,data,pack=PACK,structure=STRUCTURE)
        self.assertEqual(rule(result,"EXP_S05_03")["decision"],"blocked_conflicting_evidence")

    def test_fragment_grammar_mismatch_blocks_even_when_wording_hash_matches(self):
        pack = copy.deepcopy(self.pack)
        candidate = next(r for r in pack["rules"] if r["id"] == "EXP_S03_01")
        fragment = "Synthetic source heading"
        candidate["expected_english_sha256"] = hashlib.sha256(fragment.encode()).hexdigest()
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""CREATE TABLE entries (
                entry_key TEXT UNIQUE,catalogue_version TEXT,collection TEXT,source_file TEXT,
                excel_row INTEGER,structurecode TEXT,esdscom_phrase_id TEXT,original_code TEXT,
                english TEXT,sds_section INTEGER,region TEXT,phrase_owner TEXT,source TEXT,
                info TEXT,grammar TEXT
            );""")
            conn.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("h1","5.5","Core","fake.xlsx",9,candidate["structurecode"],"","",
                 fragment,3,"EU","synthetic","","","Sentence"))
        data = profile(facts={"mixture_ingredient_identity_table_prepared":fact()})
        result = evaluate_sections(self.db,data,pack=pack,structure=STRUCTURE)
        self.assertEqual(rule(result,"EXP_S03_01")["decision"],"blocked_catalogue_mismatch")

    def test_pack_rejects_missing_section_and_forged_regulatory_review(self):
        changed = copy.deepcopy(PACK)
        changed["rules"] = [x for x in changed["rules"] if x["section"] != 16]
        with self.assertRaises(RecommendationError):
            validate_candidates(changed, STRUCTURE)
        changed = copy.deepcopy(PACK)
        changed["rules"][0]["review_status"] = "legally_required"
        with self.assertRaises(RecommendationError):
            validate_candidates(changed, STRUCTURE)
        changed = copy.deepcopy(PACK)
        changed["rules"][0]["expected_english_sha256"] = "wrong"
        with self.assertRaises(RecommendationError):
            validate_candidates(changed, STRUCTURE)

    def test_no_copyrighted_wording_stored_in_rulepack(self):
        self.assertTrue(all("expected_english" not in rule for rule in PACK["rules"]))
        self.assertTrue(all(len(rule["expected_english_sha256"]) == 64 for rule in PACK["rules"]))


class SectionRecommendationsAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0),
                                      create_handler(Path("/not/installed/catalogue.sqlite")))
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.thread.join(timeout=5)

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=5)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        try:
            c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            r = c.getresponse()
            text = r.read().decode("utf-8")
            return r.status, json.loads(text) if path.startswith("/api/") else text
        finally:
            c.close()

    def test_config_and_page(self):
        code, config = self.req("GET", "/api/section-recommendations/config")
        self.assertEqual(code, 200)
        self.assertEqual(len(config["sections"]), 16)
        self.assertEqual(len(config["rules"]), 105)
        code, html = self.req("GET", "/section_recommendations.html")
        self.assertEqual(code, 200)
        self.assertIn("Phrase", html)

    def test_local_api_no_db_does_not_guess_phrase(self):
        code, data = self.req("POST", "/api/section-recommendations/evaluate", profile(
            facts={"tightly_closed_storage_confirmed_safe": fact()}))
        self.assertEqual(code, 200)
        self.assertEqual(len(data["sections"]), 16)
        self.assertEqual(rule(data, "R07_SEALED_STORAGE")["decision"], "blocked_catalogue_mismatch")
        self.assertFalse(data["sds_compliant"])

    def test_invalid_input_returns_400(self):
        code, data = self.req("POST", "/api/section-recommendations/evaluate", {"jurisdiction": "EU"})
        self.assertEqual(code, 400)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
