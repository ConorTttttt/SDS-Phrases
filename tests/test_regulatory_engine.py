"""Synthetic v0.2 evaluator tests. No legally verified rule mappings are used."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from regulatory_engine import (RegulatoryError,evaluate_regulations,validate_pack,validate_product)

PACK=json.loads((ROOT/"rules"/"regulatory-demo-v0.2.json").read_text(encoding="utf-8"))

def product(**changes):
    base={
      "jurisdiction":"EU","as_of":"2026-11-08","hazards":["H315","H319"],
      "classification_complete":{"value":"yes","evidence":"Synthetic classification review"},
      "facts":{
        "skin_contact_possible":{"value":"yes","evidence":"Synthetic exposure scenario"},
        "eye_contact_possible":{"value":"yes","evidence":"Synthetic exposure scenario"},
        "storage_information_assessed":{"value":"yes","evidence":"Synthetic storage assessment"},
      },
      "attributes":{"physical_form":{"value":"liquid","evidence":"Synthetic product specification"}}
    }
    base.update(changes)
    return base

def byid(result, rule):
    return next(x for x in result["decisions"] if x["rule_id"]==rule)

class RegulatoryStageATests(unittest.TestCase):
    def test_all_demo_rules_never_claim_legal_requirement(self):
        r=evaluate_regulations(PACK,product())
        self.assertEqual(len(r["decisions"]),3)
        self.assertEqual({x["decision"] for x in r["decisions"]},{"candidate_unverified"})
        self.assertTrue(all(x["publishable"] is False for x in r["decisions"]))
        self.assertFalse(r["sds_compliance_established"])
        self.assertEqual(r["coverage"][3]["coverage_status"],"partial_unverified")
        self.assertEqual(len(r["coverage"]),16)
        self.assertEqual(r["coverage"][0]["coverage_status"],"no_rules_in_pack")

    def test_unknown_fact_needs_information_not_false(self):
        data=product()
        data["facts"].pop("skin_contact_possible")
        r=evaluate_regulations(PACK,data)
        p=byid(r,"DEMO_H315_SKIN_REVIEW")
        self.assertEqual(p["decision"],"information_required")
        self.assertIn("facts.skin_contact_possible",p["missing_information"])

    def test_unknown_or_unevidenced_fact(self):
        data=product()
        data["facts"]["skin_contact_possible"]={"value":"unknown","evidence":""}
        self.assertEqual(byid(evaluate_regulations(PACK,data),"DEMO_H315_SKIN_REVIEW")["decision"],"information_required")
        data["facts"]["skin_contact_possible"]={"value":"yes","evidence":""}
        self.assertEqual(byid(evaluate_regulations(PACK,data),"DEMO_H315_SKIN_REVIEW")["decision"],"information_required")

    def test_explicit_negative_fact_is_not_triggered(self):
        data=product()
        data["facts"]["skin_contact_possible"]={"value":"no","evidence":"Synthetic documented no exposure"}
        self.assertEqual(byid(evaluate_regulations(PACK,data),"DEMO_H315_SKIN_REVIEW")["decision"],"not_triggered_unverified")

    def test_absent_hazard_not_safely_inferred_if_classification_incomplete(self):
        data=product(hazards=["H319"],classification_complete={"value":"unknown","evidence":""})
        r=evaluate_regulations(PACK,data)
        p=byid(r,"DEMO_H315_SKIN_REVIEW")
        self.assertEqual(p["decision"],"information_required")
        self.assertIn("classification_complete",p["missing_information"])

    def test_absent_hazard_with_completed_assessment_is_negative(self):
        data=product(hazards=["H319"])
        self.assertEqual(byid(evaluate_regulations(PACK,data),"DEMO_H315_SKIN_REVIEW")["decision"],"not_triggered_unverified")

    def test_jurisdiction_is_always_scoped(self):
        data=product(jurisdiction="GB")
        result=evaluate_regulations(PACK,data)
        self.assertEqual({r["decision"] for r in result["decisions"]},{"outside_jurisdiction"})
        self.assertEqual(result["coverage"][3]["coverage_status"],"no_rules_in_pack")

    def test_dates_are_inclusive_and_expiration_is_neutral(self):
        r=copy.deepcopy(PACK)
        r["rules"][0]["effective_from"]="2026-11-08"
        r["rules"][0]["effective_until"]="2026-11-08"
        self.assertEqual(byid(evaluate_regulations(r,product()),"DEMO_H315_SKIN_REVIEW")["decision"],"candidate_unverified")
        self.assertEqual(byid(evaluate_regulations(r,product(as_of="2026-11-09")),"DEMO_H315_SKIN_REVIEW")["decision"],"outside_effective_dates")

    def test_condition_trace_contains_provenance(self):
        r=evaluate_regulations(PACK,product())
        p=byid(r,"DEMO_H315_SKIN_REVIEW")
        self.assertEqual(p["regulatory_source"]["instrument"],"internal_draft")
        self.assertIn("H315",p["matched_hazards"])
        self.assertEqual(p["trace"]["operator"],"all")
        self.assertEqual(p["trace"]["children"][1]["evidence"],"Synthetic exposure scenario")

    def test_rule_schema_rejects_unsupported_operator_and_duplicate_ids(self):
        pack=copy.deepcopy(PACK)
        pack["rules"][0]["when"]={"script":"eval"}
        with self.assertRaises(RegulatoryError): validate_pack(pack)
        pack=copy.deepcopy(PACK)
        pack["rules"].append(copy.deepcopy(pack["rules"][0]))
        with self.assertRaises(RegulatoryError): validate_pack(pack)

    def test_marking_verified_without_audit_is_rejected(self):
        pack=copy.deepcopy(PACK)
        pack["rules"][0]["review_status"]="independently_verified"
        with self.assertRaises(RegulatoryError): validate_pack(pack)
        pack["rules"][0]["verification"]={"reviewer":"Someone","audit_reference":"synthetic-audit",
                 "verified_at":"2026-11-08","source_locator":"Synthetic-source §X"}
        with self.assertRaises(RegulatoryError): validate_pack(pack) # Internal drafts prohibited

    def test_valid_synthetic_verified_rule_can_exercise_required_path(self):
        pack=copy.deepcopy(PACK)
        r=pack["rules"][0]
        r["review_status"]="independently_verified"
        r["intended_effect"]="required"
        r["source"]["instrument"]="synthetic_test_instrument"
        r["verification"]={"reviewer":"Test Reviewer","audit_reference":"test-only-A1",
                 "verified_at":"2026-11-08","source_locator":"fictional://test/section1"}
        result=evaluate_regulations(pack,product())
        match=byid(result,"DEMO_H315_SKIN_REVIEW")
        self.assertEqual(match["decision"],"required")
        self.assertFalse(match["publishable"]) # still requires human release and verified external source
        self.assertFalse(result["sds_compliance_established"])

    def test_boolean_operators_propagate_unknown_correctly(self):
        pack=copy.deepcopy(PACK)
        pack["rules"][0]["when"]={"any":[{"fact_equals":{"key":"not_known","value":"yes"}},
                                           {"fact_equals":{"key":"skin_contact_possible","value":"yes"}}]}
        result=evaluate_regulations(pack,product())
        self.assertEqual(byid(result,"DEMO_H315_SKIN_REVIEW")["decision"],"candidate_unverified")
        pack["rules"][0]["when"]={"not":{"fact_equals":{"key":"not_known","value":"yes"}}}
        result=evaluate_regulations(pack,product())
        self.assertEqual(byid(result,"DEMO_H315_SKIN_REVIEW")["decision"],"information_required")

    def test_invalid_dates_fact_types_and_empty_evidence_do_not_grant_completeness(self):
        for data in (
            product(as_of="2026-02-30"),
            product(facts={"eye_contact_possible":{"value":True,"evidence":"No"}}),
            product(hazards=["H315",4]),
            product(classification_complete={"value":"yes","evidence":4}),
        ):
            with self.subTest(data=data),self.assertRaises(RegulatoryError):
                validate_product(data)
        data=product(hazards=[],classification_complete={"value":"yes","evidence":""})
        self.assertEqual(byid(evaluate_regulations(PACK,data),"DEMO_H315_SKIN_REVIEW")["decision"],"information_required")

if __name__=="__main__":
    unittest.main()
