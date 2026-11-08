import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from src.engine import SelectionError, evaluate, validate_input

ROOT = Path(__file__).resolve().parents[1]
RULES = json.loads((ROOT / "rules" / "pilot-eu-gb-v1.json").read_text())

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "fixture.sqlite"
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("""CREATE TABLE entries (
                entry_key TEXT, collection TEXT, structurecode TEXT, esdscom_phrase_id TEXT,
                original_code TEXT, english TEXT, sds_section INTEGER, region TEXT,
                source TEXT, revision_date_raw TEXT, phrase_owner TEXT, catalogue_version TEXT
            )""")
            conn.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                ("test-EU-skin", "Core", "01.04.01.03.18000.", "", "", "After contact with skin, wash immediately with plenty of water and soap.", 4, "EU", "", "", "eSDScom", "5.5"),
                ("test-EU-store", "Core", "01.07.02.02.13000.", "", "S7", "Keep container tightly closed.", 7, "EU", "", "", "eSDScom", "5.5"),
                ("test-GB-skin", "Core", "02.04.01.03.18000.", "", "", "After contact with skin, wash immediately with plenty of water and soap.", 4, "GB", "", "", "eSDScom", "5.5"),
            ])
    def tearDown(self):
        self.temp.cleanup()

    def test_evidence_gated_selection(self):
        result = evaluate(self.db, RULES, {
            "jurisdiction": "EU", "hazards": ["H315"],
            "facts": {"skin_first_aid_reviewed": True}})
        self.assertEqual([r["rule_id"] for r in result["selected"]], ["FIRST_AID_SKIN"])
        self.assertTrue(result["selected"][0]["review_required"])
        self.assertEqual(result["selected"][0]["catalogue"]["structurecode"], "01.04.01.03.18000.")

    def test_pending_evidence_no_unverified_phrase(self):
        result = evaluate(self.db, RULES, {"jurisdiction": "EU", "hazards": ["H315"], "facts": {}})
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["pending_evidence"][0]["rule_id"], "FIRST_AID_SKIN")

    def test_fact_only_rule_does_not_auto_fire(self):
        result = evaluate(self.db, RULES, {"jurisdiction": "EU", "hazards": [], "facts": {}})
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["pending_evidence"], [])

    def test_fact_only_rule_fires_with_evidence(self):
        result = evaluate(self.db, RULES, {"jurisdiction": "EU", "hazards": [],
                                          "facts": {"sealed_storage_verified": True}})
        self.assertEqual([r["rule_id"] for r in result["selected"]], ["STORAGE_CONTAINER_CLOSED"])

    def test_gb_uses_gb_code(self):
        result = evaluate(self.db, RULES, {"jurisdiction": "GB", "hazards": ["H315"],
                                          "facts": {"skin_first_aid_reviewed": True}})
        self.assertEqual(result["selected"][0]["catalogue"]["structurecode"], "02.04.01.03.18000.")

    def test_wrong_jurisdiction_not_cross_selected(self):
        result = evaluate(self.db, RULES, {"jurisdiction": "US", "hazards": ["H315"],
                                          "facts": {"skin_first_aid_reviewed": True}})
        self.assertEqual(result["selected"], [])

    def test_changed_wording_blocks_instead_of_replacing(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE entries SET english='ALTERNATE' WHERE entry_key='test-EU-skin'")
        result = evaluate(self.db, RULES, {"jurisdiction": "EU", "hazards": ["H315"],
                                          "facts": {"skin_first_aid_reviewed": True}})
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["blocked_matches"][0]["rule_id"], "FIRST_AID_SKIN")

    def test_other_catalogue_version_blocks(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE entries SET catalogue_version='5.4' WHERE entry_key='test-EU-skin'")
        result = evaluate(self.db, RULES, {"jurisdiction": "EU", "hazards": ["H315"],
                                          "facts": {"skin_first_aid_reviewed": True}})
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["blocked_matches"][0]["rule_id"], "FIRST_AID_SKIN")

    def test_non_string_hazard_rejected(self):
        with self.assertRaises(SelectionError):
            validate_input({"hazards": ["H315", 315]})

    def test_no_database_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            evaluate(self.db.with_name("missing.sqlite"), RULES, {"jurisdiction": "EU"})

    def test_reject_unknown_jurisdiction(self):
        with self.assertRaises(SelectionError):
            validate_input({"jurisdiction": "UN"})

    def test_reject_invalid_hazard(self):
        with self.assertRaises(SelectionError):
            validate_input({"hazards": ["H315", "TEST"]})

    def test_reject_unknown_fact(self):
        with self.assertRaises(SelectionError):
            validate_input({"facts": {"evidence_is_good": True}})

    def test_reject_nonboolean_fact(self):
        with self.assertRaises(SelectionError):
            validate_input({"facts": {"sealed_storage_verified": "true"}})

if __name__ == "__main__":
    unittest.main()
