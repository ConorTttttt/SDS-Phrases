"""Evidence-gated, section-by-section SDS phrase suggestions.

Produces *unverified drafting candidates only* from exact eSDScom Core 5.5
wording and structure codes. It never determines the legal applicability of
a phrase, asserts mandatory statements, or certifies SDS content completeness.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from regulatory_engine import (
    RegulatoryError,
    evaluate_evidence_condition,
    validate_product,
)

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "section_phrase_candidates_v0.1.json"
STRUCTURE = ROOT / "rules" / "eu_reach_annex2_partb_2026.json"
EXPECTED_SCHEMA = "sds-section-phrase-recommendations/v0.1"
EXPECTED_VERSION = "5.5"
ALLOWED_STATES = {"yes", "no", "unknown"}
FACT_KEY = re.compile(r"^[a-z][a-z0-9_]*$")


class RecommendationError(ValueError):
    pass


def load_candidates():
    """Read the curated rule pack without reading the licensed local database."""
    pack = json.loads(RULES.read_text(encoding="utf-8"))
    structure = json.loads(STRUCTURE.read_text(encoding="utf-8"))
    validate_candidates(pack, structure)
    return pack


def _rule_facts(node):
    op, value = next(iter(node.items()))
    if op in ("all", "any"):
        result = set()
        for item in value:
            result |= _rule_facts(item)
        return result
    if op == "not":
        return _rule_facts(value)
    if op == "fact_equals":
        return {value["key"]}
    return set()


def _all_nodes(trace):
    yield trace
    for child in trace.get("children", ()):
        yield from _all_nodes(child)


def validate_candidates(pack, structure):
    if not isinstance(pack, dict) or pack.get("schema") != EXPECTED_SCHEMA:
        raise RecommendationError("Unsupported section-phrase pack schema")
    if pack.get("catalogue_version") != EXPECTED_VERSION:
        raise RecommendationError("Unexpected eSDScom catalogue version")
    if pack.get("jurisdiction") != "EU":
        raise RecommendationError("Unexpected jurisdiction in section-phrase pack")
    if structure.get("schema") != "reach-annex2-part-b-structure/v0.1":
        raise RecommendationError("Unsupported SDS section structure")
    rules = pack.get("rules")
    if not isinstance(rules, list) or not 1 <= len(rules) <= 300:
        raise RecommendationError("Invalid curated phrase rule collection")
    sections = {int(s["code"]) for s in structure["sections"]}
    if sections != set(range(1, 17)):
        raise RecommendationError("The source section inventory is incomplete")
    unique_rules, unique_codes = set(), set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise RecommendationError("Curated phrase rules must be objects")
        rid, section, code = rule.get("id"), rule.get("section"), rule.get("structurecode")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", rid) or rid in unique_rules:
            raise RecommendationError("Invalid or duplicate curated rule ID")
        unique_rules.add(rid)
        if type(section) is not int or section not in sections:
            raise RecommendationError(rid + ": invalid SDS section")
        if not isinstance(code, str) or not code.startswith("01." + f"{section:02d}" + ".") or code in unique_codes:
            raise RecommendationError(rid + ": repeated or cross-jurisdiction structure code")
        unique_codes.add(code)
        if rule.get("collection") != "Core":
            raise RecommendationError(rid + ": only the Core catalogue is in scope")
        fingerprint = rule.get("expected_english_sha256")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise RecommendationError(rid + ": missing source wording SHA-256")
        grammar = rule.get("expected_grammar")
        if grammar is not None and grammar not in ("Sentence", "List-Element", "List-Start", "Header", "Other"):
            raise RecommendationError(rid + ": invalid catalogue grammar")
        subsection = rule.get("subsection_hint")
        if subsection is not None and (
            not isinstance(subsection, str) or
            not re.fullmatch(re.escape(str(section)) + r"(?:\.[1-9][0-9]?)?", subsection)
        ):
            raise RecommendationError(rid + ": invalid subsection hint")
        if not isinstance(rule.get("review_note"), str) or not rule["review_note"].strip():
            raise RecommendationError(rid + ": missing reviewer warning")
        if rule.get("review_status") != "draft_nonbinding_human_review_required":
            raise RecommendationError(rid + ": review status must be draft")
        if rule.get("reference", {}).get("selection_basis", "").find("no regulatory applicability approval") < 0:
            raise RecommendationError(rid + ": missing legal limitation")
        # Evaluate a fully unknown product to validate the condition grammar.
        try:
            evaluate_evidence_condition(rule["when"], {
                "jurisdiction": "EU",
                "as_of": "2026-11-08",
                "hazards": [],
                "classification_complete": {"value": "unknown", "evidence": ""},
                "facts": {},
                "attributes": {},
            })
        except (KeyError, RegulatoryError) as exc:
            raise RecommendationError(rid + ": invalid evidence condition: " + str(exc)) from exc
        if not all(FACT_KEY.fullmatch(f) for f in _rule_facts(rule["when"])):
            raise RecommendationError(rid + ": invalid evidence fact")
    if {rule["section"] for rule in rules} != sections:
        raise RecommendationError("Each of the 16 SDS sections needs a candidate path")
    return pack


def _matching_catalogue_record(conn, rule):
    if conn is None:
        return None, "Local phrase catalogue not installed or unreadable."
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT entry_key,catalogue_version,collection,source_file,excel_row,
                      structurecode,esdscom_phrase_id,original_code,english,sds_section,
                      region,phrase_owner,source,info,grammar
               FROM entries WHERE collection=? AND structurecode=?""",
            (rule["collection"], rule["structurecode"]),
        ).fetchall()
    except sqlite3.Error:
        return None, "Local phrase catalogue schema is unavailable or incompatible."
    if len(rows) != 1:
        return None, "Expected exactly one source entry; missing or duplicated structure code."
    row = dict(rows[0])
    if (row["catalogue_version"] != EXPECTED_VERSION or
        not row["english"] or
        hashlib.sha256(row["english"].encode("utf-8")).hexdigest() != rule["expected_english_sha256"] or
        row["sds_section"] != rule["section"] or
        (rule.get("expected_grammar") is not None and row["grammar"] != rule["expected_grammar"])):
        return None, "Catalogue wording, version or SDS section does not match the curated reference."
    return row, None


def evaluate_sections(catalogue_path, product, pack=None, structure=None):
    """Every section is returned, even where no phrase can be recommended."""
    validate_product(product)
    pack = pack or load_candidates()
    structure = structure or json.loads(STRUCTURE.read_text(encoding="utf-8"))
    validate_candidates(pack, structure)
    catalogue_path = Path(catalogue_path)
    conn = None
    if catalogue_path.is_file():
        try:
            conn = sqlite3.connect(str(catalogue_path))
        except sqlite3.Error:
            conn = None
    def affirmed(key):
        record = product.get("facts", {}).get(key, {})
        return (record.get("value") == "yes" and
                isinstance(record.get("evidence"), str) and
                bool(record["evidence"].strip()))

    conflict_names = ("substance_csa_performed_verified", "substance_csa_not_performed_verified")
    contradictory = all(affirmed(key) for key in conflict_names)
    contradictory_keys = set(conflict_names) if contradictory else set()
    state_keys = {
        "physical_state_liquid_verified", "physical_state_solid_verified",
        "physical_state_gas_verified"
    }
    if sum(affirmed(key) for key in state_keys) > 1:
        contradictory_keys.update(state_keys)
    if affirmed("mixture_not_classified_under_clp_reviewed") and (
        affirmed("eu_clp_hazardous_mixture_confirmed") or
        any(h.startswith("H") for h in product["hazards"])
    ):
        contradictory_keys.add("mixture_not_classified_under_clp_reviewed")
        contradictory_keys.add("eu_clp_hazardous_mixture_confirmed")
    if affirmed("substance_not_classified_under_clp_reviewed") and any(
        h.startswith("H") for h in product["hazards"]
    ):
        contradictory_keys.add("substance_not_classified_under_clp_reviewed")
    if affirmed("product_non_combustible_confirmed") and any(
        h in {"H220", "H221", "H222", "H223", "H224", "H225", "H226", "H228"}
        for h in product["hazards"]
    ):
        contradictory_keys.add("product_non_combustible_confirmed")
    decisions = []
    try:
        for rule in pack["rules"]:
            base = {
                "rule_id": rule["id"],
                "section": rule["section"],
                "topic": rule["topic"],
                "subsection_hint": rule.get("subsection_hint", ""),
                "expected_grammar": rule.get("expected_grammar", "not_pinned"),
                "source_structurecode": rule["structurecode"],
                "source_collection": rule["collection"],
                "review_note": rule["review_note"],
                "source_context": rule["reference"],
                "review_status": rule["review_status"],
                "decision": "",
                "explanation": "",
                "missing_information": [],
                "matched_hazards": [],
                "trace": None,
                "phrase": None,
                "source": None,
                "legally_required": False,
                "approved_for_sds": False,
            }
            if product["jurisdiction"] != pack["jurisdiction"]:
                base["decision"] = "outside_jurisdiction"
                base["explanation"] = "Only EU-format catalogue suggestions were curated in this pack."
            elif _rule_facts(rule["when"]) & contradictory_keys:
                base["decision"] = "blocked_conflicting_evidence"
                base["explanation"] = ("Conflicting evidenced product facts or an incompatible hazard "
                                       "classification were supplied. Reconcile before suggesting text.")
            else:
                trace = evaluate_evidence_condition(rule["when"], product)
                base["trace"] = trace
                leaves = list(_all_nodes(trace))
                base["matched_hazards"] = sorted({
                    h for leaf in leaves for h in leaf.get("matched_hazards", [])
                })
                if trace["status"] == "unknown":
                    base["decision"] = "evidence_required"
                    base["missing_information"] = sorted({
                        missing for leaf in leaves for missing in leaf.get("missing", [])
                    })
                    base["explanation"] = "Missing or unevidenced product information; no phrase selected."
                elif trace["status"] == "no":
                    base["decision"] = "not_triggered"
                    base["explanation"] = "Curated authoring condition does not match the provided evidence."
                else:
                    row, failure = _matching_catalogue_record(conn, rule)
                    if failure:
                        base["decision"] = "blocked_catalogue_mismatch"
                        base["explanation"] = failure + " No fallback phrase is substituted."
                    else:
                        base["decision"] = "draft_candidate"
                        base["phrase"] = row["english"]
                        base["source"] = row
                        base["explanation"] = "Documented input matches an unverified drafting suggestion. Expert review required."
            decisions.append(base)
    finally:
        if conn is not None:
            conn.close()
    sections = []
    for item in structure["sections"]:
        sec = int(item["code"])
        scoped = [d for d in decisions if d["section"] == sec]
        counts = {
            status: sum(d["decision"] == status for d in scoped)
            for status in ("draft_candidate", "evidence_required", "not_triggered",
                           "blocked_catalogue_mismatch", "blocked_conflicting_evidence",
                           "outside_jurisdiction")
        }
        sections.append({
            "section": sec, "heading": item["heading"],
            "recommendations": scoped,
            "counts": counts,
            "review_status": "draft_only",
            "section_content_validated": False,
            "complete": False,
        })
    return {
        "schema": EXPECTED_SCHEMA,
        "pack_id": pack["id"],
        "pack_version": pack["version"],
        "catalogue_version": pack["catalogue_version"],
        "jurisdiction": product["jurisdiction"],
        "as_of": product["as_of"],
        "catalogue_installed": conn is not None,
        "sections": sections,
        "counts": {key: sum(section["counts"][key] for section in sections)
                   for key in sections[0]["counts"]},
        "sds_compliant": False, "phrases_approved": False,
        "date_applicability_reviewed": False,
        "warning": "Draft source-text options only: exact eSDScom wording is not legal selection authority. All 16 sections need product-specific content and expert regulatory review. A missing suggestion never means that the section is complete."
    }
