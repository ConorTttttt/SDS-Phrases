"""Controlled executable regulatory evaluators (Task 24): registry, gate, three-valued logic, traces, integration."""
import copy
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "gemini/roles"))
import canonical_requirements as c
import regulatory_evaluators as e

EV = "Synthetic fixture only"


def F(value):
    return {"value": value, "evidence": EV}


def base(**extra):
    record = {"jurisdiction": "EU", "as_of": "2026-06-22", "title_iv_in_scope": F("yes"), "product_type": F("mixture")}
    record.update(extra)
    return record


def ingredient(iid, flag, flag_value, **conc):
    return {"id": iid, "flags": {flag: F(flag_value)}, "concentration": dict(conc, evidence=EV)}


def request_mixture(*ingredients, phase="non_gaseous", **extra):
    fields = dict(hazardous=F("no"), recipient_request=F("yes"), mixture_phase=F(phase), ingredients=list(ingredients))
    fields.update(extra)
    return base(**fields)


CARC = "EU-REACH-A31-REQUEST-CARC2"
HAZ = "EU-REACH-A31-REQUEST-HAZARD"
SUPPLY = "EU-REACH-A31-SUPPLY-HAZARDOUS"


class Registry(unittest.TestCase):
    def setUp(self):
        self.registry = e.load_registry()

    def test_registry_binds_current_versions_only_to_approved_functions(self):
        current = {r["id"]: r for r in c.all_requirements()}
        self.assertEqual(len(current), 369)
        self.assertEqual(len(self.registry["bindings"]), 16)
        for b in self.registry["bindings"]:
            self.assertEqual(b["rule_version"], c.requirement_version(current[b["requirement_id"]]))
            self.assertIn(b["evaluator"], e.EVALUATORS)
            self.assertEqual(current[b["requirement_id"]]["implementation_status"], "manual_review_only")
        cov = e.registry_coverage()
        self.assertEqual((cov["bound_to_executable_evaluator"], cov["manual_review_only"], cov["promotion_gate_open"]), (16, 353, 0))

    def invalid(self, mutate, message):
        registry = copy.deepcopy(self.registry)
        mutate(registry)
        with self.assertRaisesRegex(e.EvaluatorError, message):
            e.validate_registry(registry)

    def test_invalid_evaluator_definitions(self):
        b0 = lambda r: r["bindings"][0]
        carc = lambda r: next(b for b in r["bindings"] if b["requirement_id"] == CARC)
        cases = [
            (lambda r: r.update(schema="other"), "schema"),
            (lambda r: b0(r).update(evaluator="__import__('os').system('id')"), "not an approved implementation"),
            (lambda r: b0(r).update(evaluator="eval"), "not an approved implementation"),
            (lambda r: b0(r).update(code="lambda x: 'yes'"), "forbidden or unknown keys"),
            (lambda r: b0(r).update(expression="1==1"), "forbidden or unknown keys"),
            (lambda r: b0(r).update(regulatory_verification_status=e.VERIFIED), "forbidden or unknown keys"),
            (lambda r: b0(r).update(decision_effect="determinative"), "forbidden or unknown keys"),
            (lambda r: b0(r).update(rule_version="0" * 64), "neither current nor archived"),
            (lambda r: b0(r).update(evaluator_version="9.9.9"), "evaluator version mismatch"),
            (lambda r: b0(r).update(software_implementation_status="verified"), "software implementation status"),
            (lambda r: b0(r)["runtime_validation"].update(tests=["tests/does_not_exist.py"]), "runtime validation"),
            (lambda r: b0(r)["parameters"].update(branch="anything"), "Unknown Article 31"),
            (lambda r: b0(r)["parameters"].update(extra="x"), "Unknown evaluator parameters"),
            (lambda r: r["bindings"].append(copy.deepcopy(b0(r))), "Duplicate binding"),
            (lambda r: carc(r)["parameters"]["phase_thresholds"]["non_gaseous"].update(value="0.2"), "value differs from source"),
            (lambda r: carc(r)["parameters"]["phase_thresholds"]["non_gaseous"].update(unit="% v/v"), "unit differs from source"),
            (lambda r: carc(r)["parameters"]["phase_thresholds"]["non_gaseous"].update(source_text="≥ 0,5 % by weight"), "not found in canonical wording"),
            (lambda r: carc(r)["parameters"]["phase_thresholds"]["non_gaseous"].update(operator=">"), "operator differs"),
            (lambda r: carc(r)["parameters"]["phase_thresholds"].update(gaseous=dict(source_text="≥ 0,2 % by volume", operator=">=", value="0.2", unit="% v/v")), "not found in canonical wording"),
        ]
        for mutate, message in cases:
            with self.subTest(message=message):
                self.invalid(mutate, message)

    def test_registry_json_contains_no_code_and_module_never_evaluates_code(self):
        text = (ROOT / "regulatory/canonical/evaluators.json").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\blambda\b|\bimport\b|\beval\s*\(|\bexec\s*\(|__|\bdef ", text))
        source = (ROOT / "src/regulatory_evaluators.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?<![\w.])(eval|exec|compile|__import__|getattr|setattr)\s*\(|\bimportlib\b|\bpickle\b", source))

    def test_caller_supplied_registry_is_validated(self):
        registry = copy.deepcopy(self.registry)
        registry["bindings"][0]["evaluator"] = "os.system"
        with self.assertRaises(e.EvaluatorError):
            e.evaluate(SUPPLY, base(), registry)

    def test_historic_rule_version_binding_is_preserved_and_exact(self):
        clp = c.load_clp()
        hist = clp["historical_versions"][0]["record"]
        version = c.requirement_version(hist)
        current = next(r for r in clp["requirements"] if r["id"] == hist["id"])
        self.assertNotEqual(version, c.requirement_version(current))
        registry = copy.deepcopy(self.registry)
        registry["bindings"].append(dict(copy.deepcopy(next(b for b in registry["bindings"] if b["evaluator"] == "sds_dated")),
                                         requirement_id=hist["id"], rule_version=version))
        e.validate_registry(registry)
        old = e.evaluate(hist["id"], base(sds_date=F("2026-01-01")), registry, rule_version=version)
        self.assertEqual((old["rule_version"], old["evaluator"]), (version, "sds_dated"))
        now = e.evaluate(hist["id"], base(sds_date=F("2026-01-01")), registry)
        self.assertIsNone(now["evaluator"])
        self.assertEqual(now["assessment_status"], e.REVIEW)
        self.assertIn("exact rule version", now["explanation"])


class Logic(unittest.TestCase):
    def test_missing_information_is_never_absence(self):
        empty = e.evaluate(SUPPLY, {})
        self.assertEqual((empty["outcome"], empty["assessment_status"]), ("unknown", e.INSUFFICIENT))
        self.assertIn("as_of", empty["missing_information"])
        no_facts = e.evaluate(SUPPLY, {"as_of": "2026-06-22"})
        self.assertEqual(no_facts["assessment_status"], e.INSUFFICIENT)
        self.assertEqual(set(no_facts["missing_information"]), {"title_iv_in_scope", "product_type", "hazardous"})
        unevidenced = e.evaluate(SUPPLY, base(hazardous={"value": "yes", "evidence": " "}))
        self.assertEqual(unevidenced["outcome"], "unknown")
        absent = e.evaluate(CARC, request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="0.05", unit="% w/w")))
        self.assertEqual(absent["outcome"], "unknown")
        self.assertIn("composition_complete", absent["missing_information"])
        complete = e.evaluate(CARC, request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="0.05", unit="% w/w"),
                                                    composition_complete=F("yes")))
        self.assertEqual(complete["outcome"], "no")
        self.assertEqual(complete["assessment_status"], e.REVIEW)

    def test_boolean_conditions_are_advisory_while_gate_closed(self):
        yes = e.evaluate(SUPPLY, base(hazardous=F("yes")))
        self.assertEqual(yes["outcome"], "yes")
        self.assertEqual(yes["assessment_status"], e.REVIEW)
        self.assertEqual(yes["decision_effect"], "advisory_pending_regulatory_verification")
        self.assertFalse(yes["verification"]["promotion_gate"]["open"])
        self.assertFalse(yes["legal_compliance_determined"])
        no = e.evaluate(SUPPLY, base(hazardous=F("no")))
        self.assertEqual(no["outcome"], "no")
        pbt_mixture = e.evaluate("EU-REACH-A31-SUPPLY-PBT-VPVB", base(pbt_vpvb=F("yes")))
        self.assertEqual(pbt_mixture["outcome"], "no")
        exc = e.evaluate("EU-REACH-A31-GENERAL-PUBLIC-EXCEPTION", base(hazardous=F("yes"), offered_or_sold_to_general_public=F("yes"),
                         public_safety_information_sufficient=F("yes"), downstream_user_or_distributor_request=F("yes")))
        self.assertEqual(exc["outcome"], "no")

    def test_decimal_thresholds_intervals_and_units(self):
        flag = "carcinogenic_category_2"
        cases = [
            ({"value": "0.1"}, "yes"), ({"value": "0,1"}, "yes"), ({"value": 1}, "yes"),
            ({"low": "0.2", "high": "0.5"}, "yes"), ({"low": "0.05", "high": "0.3"}, "unknown"),
            ({"low": "0.01", "high": "0.1", "high_inclusive": False}, "unknown"),
        ]
        for conc, expected in cases:
            with self.subTest(conc=conc):
                t = e.evaluate(CARC, request_mixture(ingredient("A", flag, "yes", unit="% w/w", **conc)))
                self.assertEqual(t["outcome"], expected)
        below = e.evaluate(CARC, request_mixture(ingredient("A", flag, "yes", value="0.0999", unit="% w/w"), composition_complete=F("yes")))
        self.assertEqual(below["outcome"], "no")
        mismatch = e.evaluate(CARC, request_mixture(ingredient("A", flag, "yes", value="5", unit="% v/v")))
        self.assertEqual(mismatch["outcome"], "unknown")
        self.assertIn("no conversion", json.dumps(mismatch["calculation_results"]))
        gas = e.evaluate(HAZ, request_mixture(ingredient("G", "human_health_or_environmental_hazard", "yes", value="0.2", unit="% v/v"), phase="gaseous"))
        self.assertEqual(gas["outcome"], "yes")
        solid = e.evaluate(HAZ, request_mixture(ingredient("S", "human_health_or_environmental_hazard", "yes", value="0.9", unit="% w/w"),
                                                composition_complete=F("yes")))
        self.assertEqual(solid["outcome"], "no")
        no_gas_branch = e.evaluate(CARC, request_mixture(ingredient("A", flag, "yes", value="5", unit="% v/v"), phase="gaseous"))
        self.assertEqual(no_gas_branch["outcome"], "unknown")
        self.assertTrue(any("No automatic conclusion" in n for n in no_gas_branch["notes"]))
        for bad in ({"value": 0.1}, {"value": "NaN"}, {"value": "abc"}, {"low": "0.5", "high": "0.1"}, {"value": "150"}, {"value": True}):
            with self.subTest(bad=bad), self.assertRaises(e.EvaluatorError):
                e.evaluate(CARC, request_mixture(ingredient("A", flag, "yes", unit="% w/w", **bad)))

    def test_conditional_applicability_and_exceptions(self):
        classified = e.evaluate(CARC, request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="1", unit="% w/w"), hazardous=F("yes")))
        self.assertEqual(classified["outcome"], "no")
        substance = e.evaluate(CARC, request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="1", unit="% w/w"), product_type=F("substance")))
        self.assertEqual(substance["outcome"], "no")
        no_request = e.evaluate(CARC, request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="1", unit="% w/w"), recipient_request=F("no")))
        self.assertEqual(no_request["outcome"], "no")
        self.assertTrue(any(x.startswith("Exceptions to review:") for x in classified["limitations"]))

    def test_contradictory_inputs_route_to_review(self):
        t = e.evaluate(SUPPLY, base(hazardous=F("yes"), classification_complete=F("yes"), hazard_codes=[]))
        self.assertEqual((t["outcome"], t["assessment_status"]), ("unknown", e.REVIEW))
        self.assertTrue(t["contradictions"])
        dup = request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="1", unit="% w/w"),
                              ingredient("A", "carcinogenic_category_2", "no", value="1", unit="% w/w"))
        self.assertEqual(e.evaluate(CARC, dup)["assessment_status"], e.REVIEW)
        over = request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="60", unit="% w/w"),
                               ingredient("B", "carcinogenic_category_2", "no", value="50", unit="% w/w"))
        self.assertIn("exceeds 100", " ".join(e.evaluate(CARC, over)["contradictions"]))

    def test_effective_dates_and_snapshot_limitations(self):
        early = e.evaluate("EU-REACH-AII-NO-BLANK", base(as_of="2020-06-01", structure={"headings": [], "inventory_complete": F("no")}))
        self.assertEqual(early["assessment_status"], e.NOT_ASSESSED)
        self.assertIn("precedes effective date 2021-01-01", early["explanation"])
        later = e.evaluate(SUPPLY, base(as_of="2027-01-01", hazardous=F("yes")))
        self.assertTrue(any("differs from the 2026-06-22 consolidation" in x for x in later["limitations"]))
        self.assertTrue(any("Effective date of this candidate is unresolved" in x for x in later["limitations"]))
        with self.assertRaises(e.EvaluatorError):
            e.evaluate(SUPPLY, base(as_of="22/06/2026"))
        self.assertEqual(e.evaluate(SUPPLY, base(jurisdiction="GB"))["assessment_status"], e.NOT_ASSESSED)

    def test_structural_pilot(self):
        all_heads = [str(i) for i in range(1, 17)]
        full = e.evaluate("EU-REACH-A31-HEADINGS", base(structure={"headings": all_heads, "inventory_complete": F("yes")}))
        self.assertEqual((full["outcome"], full["assessment_status"]), ("yes", e.REVIEW))
        missing = e.evaluate("EU-REACH-A31-HEADINGS", base(structure={"headings": all_heads[:-1], "inventory_complete": F("yes")}))
        self.assertEqual(missing["outcome"], "no")
        partial = e.evaluate("EU-REACH-A31-HEADINGS", base(structure={"headings": all_heads[:-1], "inventory_complete": F("no")}))
        self.assertEqual(partial["outcome"], "unknown")
        blank = e.evaluate("EU-REACH-AII-NO-BLANK", base(structure={"headings": ["1", "1.1"], "inventory_complete": F("yes"), "blank_subsections": ["1.1"]}))
        self.assertEqual(blank["outcome"], "no")
        dated = e.evaluate("EU-REACH-A31-DATE", base(sds_date=F("2026-05-01")))
        self.assertEqual(dated["outcome"], "yes")
        with self.assertRaises(e.EvaluatorError):
            e.evaluate("EU-REACH-A31-HEADINGS", base(structure={"headings": ["99"], "inventory_complete": F("yes")}))


class GateAndSources(unittest.TestCase):
    def test_unsupported_and_unknown_rule_versions(self):
        unknown = e.evaluate(SUPPLY, base(hazardous=F("yes")), rule_version="0" * 64)
        self.assertEqual((unknown["assessment_status"], unknown["evaluator"]), (e.NOT_ASSESSED, None))
        record = copy.deepcopy(next(r for r in c.load_title_iv()["requirements"] if r["id"] == SUPPLY))
        record["wording"] += " (edited)"
        changed = e.evaluate(SUPPLY, base(hazardous=F("yes")), record=record)
        self.assertEqual((changed["assessment_status"], changed["evaluator"]), (e.REVIEW, None))
        self.assertIsNone(e.evaluate("EU-REACH-AII-COMPETENT-PERSON", base())["evaluator"])

    def test_gate_cannot_be_bypassed_by_inputs_or_partial_signoff(self):
        attack = base(hazardous=F("yes"), verification_status=e.VERIFIED, promotion_gate={"open": True},
                      regulatory_signoff={k: "x" for k in e.SIGNOFF_FIELDS})
        t = e.evaluate(SUPPLY, attack)
        self.assertFalse(t["verification"]["promotion_gate"]["open"])
        self.assertEqual(t["decision_effect"], "advisory_pending_regulatory_verification")
        self.assertNotIn("verification_status", t["input_data"])
        record = copy.deepcopy(next(r for r in c.load_title_iv()["requirements"] if r["id"] == SUPPLY))
        record["verification_status"] = e.VERIFIED
        source = c.load()[2]["reach"]
        gate = e.promotion_gate(record, source)
        self.assertFalse(gate["open"])
        record["regulatory_signoff"] = {k: "synthetic" for k in e.SIGNOFF_FIELDS} | {"verified_at": "2026-11-27"}
        self.assertFalse(e.promotion_gate(record, source)["open"])
        self.assertTrue(any("currentness" in r for r in e.promotion_gate(record, source)["reasons"]))
        self.assertTrue(e.promotion_gate(record, dict(source, currentness="verified_current_for_assessment_date"))["open"])

    def test_canonical_loader_still_rejects_promoted_records(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copytree(ROOT / "regulatory", root / "regulatory")
            path = root / "regulatory/canonical/requirements.json"
            pack = json.loads(path.read_text(encoding="utf-8"))
            pack["requirements"][0]["implementation_status"] = "executable"
            path.write_text(json.dumps(pack), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No canonical deterministic legal rules approved"):
                c.load(root)

    def test_unverified_or_tampered_sources(self):
        t = e.evaluate(SUPPLY, base(hazardous=F("yes")))
        self.assertIn("Source currentness: not_verified_after_snapshot", t["limitations"])
        self.assertEqual(t["regulatory_citations"][0]["source_sha256"], c.load()[2]["reach"]["sha256"])
        record = dict(next(r for r in c.load_title_iv()["requirements"] if r["id"] == SUPPLY), source_version="1999-01-01")
        src, problem = e._source(record, c.load()[2], {"title_iv": c.load()[2]["reach"]["sha256"]})
        self.assertIsNone(src)
        self.assertIn("not registered", problem)
        _, problem = e._source(dict(record, source_version="2026-06-22"), c.load()[2], {"title_iv": "0" * 64})
        self.assertIn("hash differs", problem)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copytree(ROOT / "regulatory", root / "regulatory")
            (root / "tests").mkdir()
            shutil.copy(ROOT / "tests/test_regulatory_evaluators.py", root / "tests")
            path = root / "regulatory/source_manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["sources"][0]["sha256"] = "f" * 64
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                e.evaluate(SUPPLY, base(hazardous=F("yes")), root=root)


class Traces(unittest.TestCase):
    REQUIRED = {"requirement_id", "rule_version", "evaluator_version", "input_data", "evidence_references",
                "evaluated_conditions", "regulatory_citations", "calculation_results", "missing_information",
                "verification", "limitations", "trace_digest"}

    def test_trace_is_complete_and_reproducible(self):
        inputs = request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value="0.12", unit="% w/w"))
        first, second = e.evaluate(CARC, inputs), e.evaluate(CARC, copy.deepcopy(inputs))
        self.assertEqual(first, second)
        self.assertTrue(self.REQUIRED <= set(first))
        self.assertTrue(e.verify_trace(first))
        self.assertEqual({"regulatory_verification_status", "software_implementation_status", "runtime_validation_status",
                          "canonical_implementation_status", "promotion_gate"}, set(first["verification"]))
        self.assertEqual(first["verification"]["regulatory_verification_status"], "candidate_pending_independent_legal_and_extraction_review")
        self.assertEqual(first["verification"]["software_implementation_status"], "pilot_implemented")
        self.assertEqual(first["regulatory_citations"][0]["clause"], "Article 31(3)(b)")
        self.assertTrue(first["evidence_references"] and first["evaluated_conditions"] and first["calculation_results"])
        tampered = dict(first, outcome="no")
        self.assertFalse(e.verify_trace(tampered))
        summary = json.loads(e.calculation_summary(first))
        self.assertEqual(summary["trace_digest"], first["trace_digest"])
        self.assertNotIn("input_data", summary)


class Integration(unittest.TestCase):
    def test_toolkit_reports_executable_pilot(self):
        from toolkit import assess
        out = assess(json.loads((ROOT / "regulatory/example.synthetic.json").read_text(encoding="utf-8")))
        self.assertEqual(len(out["executable_evaluations"]), 16)
        self.assertFalse(out["legal_compliance_determined"])
        self.assertFalse(any(t["verification"]["promotion_gate"]["open"] for t in out["executable_evaluations"]))
        self.assertTrue(all(t["assessment_status"] in (e.REVIEW, e.INSUFFICIENT, e.NOT_ASSESSED) for t in out["executable_evaluations"]))

    def doc(self, context):
        return {"name": "synthetic", "sha256": "a" * 64, "pages": [{"page": 1, "text": "SECTION 1 Identification"}], "context": context}

    def test_assessment_rows_carry_traces_and_keep_history(self):
        from sds_assessment import assess
        plain = {r["id"]: r for r in assess(self.doc({}))}
        self.assertEqual(plain[SUPPLY]["status"], e.INSUFFICIENT)
        self.assertEqual(plain["EU-REACH-AII-COMPETENT-PERSON"]["decision_mode"], "manual_review_only")
        reach = base(hazardous=F("yes"))
        inventory = {"jurisdiction": "EU", "as_of": "2026-06-22", "product_type": F("mixture"),
                     "headings": [str(i) for i in range(1, 17)], "inventory_complete": F("yes"), "blank_subsections": []}
        rows = {r["id"]: r for r in assess(self.doc({"reach": reach, "verified_structure": inventory}))}
        row = rows[SUPPLY]
        self.assertEqual(row["status"], e.REVIEW)
        self.assertEqual(row["evaluator_trace"]["outcome"], "yes")
        self.assertEqual(row["rule_version"], row["evaluator_trace"]["rule_version"])
        self.assertEqual(json.loads(row["calculation"])["trace_digest"], row["evaluator_trace"]["trace_digest"])
        self.assertEqual(rows["EU-REACH-A31-HEADINGS"]["evaluator_trace"]["outcome"], "yes")
        self.assertEqual(rows["supply/article31"]["status"], plain.get("supply/article31", rows["supply/article31"])["status"])
        self.assertNotIn(e.PASS, {r["status"] for r in rows.values() if "evaluator_trace" in r})
        bad = {r["id"]: r for r in assess(self.doc({"reach": request_mixture(ingredient("A", "carcinogenic_category_2", "yes", value=0.1, unit="% w/w"))}))}
        self.assertEqual(bad[CARC]["status"], e.NOT_ASSESSED)
        self.assertIn("decimal string", bad[CARC]["explanation"])

    def test_exchange_exports_calculations_and_blocks_gate_bypass(self):
        from sds_assessment import assess
        from exchange import STATUS, DIMENSIONS, prepare, validate
        rows = assess(self.doc({"reach": base(hazardous=F("yes"))}))
        bundle = prepare(rows, "P", [SUPPLY + ":calculation"])
        self.assertIn("evaluator_trace_snapshot", bundle["sources"])
        self.assertEqual(json.loads(bundle["evidence"][0]["value"])["outcome"], "yes")
        reply = {k: v for k, v in bundle.items() if k != "evidence"}
        finding = dict(requirement_id=SUPPLY, evidence_ids=[SUPPLY + ":calculation"], source_id="reach",
                       citation="Article 31(1)(a)", status=STATUS[0], interpretation="x", requested_action="y",
                       **dict.fromkeys(DIMENSIONS, "unresolved"))
        with self.assertRaisesRegex(ValueError, "Review gate closed"):
            validate(rows, bundle, dict(reply, findings=[finding]), "P")
        ok = validate(rows, bundle, dict(reply, findings=[dict(finding, status=STATUS[6])]), "P")
        self.assertIn("pending", ok["review_status"])

    def test_authoring_report_includes_executable_results_and_fingerprint(self):
        from sds_authoring import PhraseApprovals, evaluate
        with tempfile.TemporaryDirectory() as d:
            cat = Path(d) / "catalogue.sqlite"
            with sqlite3.connect(cat) as db:
                db.execute("CREATE TABLE entries(entry_key,catalogue_version,collection,source_file,excel_row,structurecode,"
                           "esdscom_phrase_id,original_code,english,jurisdiction_structure,sds_section)")
                db.execute("CREATE TABLE catalogue_index(entry_key,wording_hash,sds_subsection,phrase_kind)")
            db.close()
            product = {"id": "A", "kind": "mixture", "jurisdiction": "EU", "language": "en", "as_of": "2026-06-22",
                       "sources": {"s": {"reference": "synthetic", "locator": "p1", "version": "1"}},
                       "data": {"formulation": {"value": [{"identity": "test", "mass_percent": 100}], "sources": ["s"]},
                                "mixture_classification": {"value": {"hazards": ["H225"], "complete": True}, "sources": ["s"]}},
                       "assessment_context": {"reach": base(hazardous=F("yes"))}}
            report = evaluate({"products": [product], "content": []}, PhraseApprovals(Path(d) / "a.sqlite", cat))
        self.assertIn("regulatory/canonical/evaluators.json", report["source_hashes"])
        executable = report["products"][0]["engines"]["executable"]
        self.assertEqual(len(executable["evaluations"]), 16)
        self.assertEqual(executable["promotion_gate_open"], 0)

    def test_coverage_outputs_separate_statuses(self):
        pack, raw, _ = c.load()
        matrix = c.coverage_matrix(pack, raw)
        self.assertEqual(matrix["executable_evaluators"]["annex_ii_targets_bound"], 1)
        targets = [t for s in matrix["sections"].values() for t in s["assessment_targets"]]
        bound = [t for t in targets if t["evaluator"]]
        self.assertEqual([t["id"] for t in bound], ["EU-REACH-AII-NO-BLANK"])
        self.assertEqual(bound[0]["verification_status"], "candidate_pending_independent_legal_and_extraction_review")
        title = c.title_iv_coverage(c.load_title_iv())
        self.assertEqual(sum(r["evaluator"] is not None for v in title.values() for r in v["requirements"]), 15)


if __name__ == "__main__":
    unittest.main()
