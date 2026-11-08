"""Deterministic, fail-closed SDS phrase candidate selector. Python stdlib only."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

JURISDICTION_PREFIX = {"EU": "01", "GB": "02", "US": "04"}
HAZARD_RE = re.compile(r"^(?:H\d{3}|EUH\d{3})$")
FACTS = {
    "inhalation_first_aid_reviewed",
    "eye_first_aid_reviewed",
    "skin_first_aid_reviewed",
    "drain_protection_verified",
    "sealed_storage_verified",
    "glove_requirements_reviewed",
    "ignition_controls_reviewed",
}


class SelectionError(ValueError):
    pass


def validate_input(payload):
    if not isinstance(payload, dict):
        raise SelectionError("Request must be an object.")
    jurisdiction = payload.get("jurisdiction", "EU")
    if jurisdiction not in JURISDICTION_PREFIX:
        raise SelectionError("Supported jurisdictions: EU, GB and US.")
    hazards = payload.get("hazards", [])
    facts = payload.get("facts", {})
    if not isinstance(hazards, list) or len(hazards) > 100:
        raise SelectionError("hazards must be an array of at most 100 codes.")
    if not isinstance(facts, dict):
        raise SelectionError("facts must be an object.")
    hazards = [x.strip().upper() for x in hazards if isinstance(x, str)]
    if any(not HAZARD_RE.fullmatch(x) for x in hazards):
        raise SelectionError("Invalid hazard code (expected Hnnn or EUHnnn).")
    if len(facts) > 100 or any(k not in FACTS or type(v) is not bool for k, v in facts.items()):
        raise SelectionError("Unknown fact or non-boolean fact value.")
    sections = payload.get("sections", [])
    if not isinstance(sections, list) or len(sections) > 16 or any(type(s) is not int or s < 1 or s > 16 for s in sections):
        raise SelectionError("sections must be an array of SDS section numbers (1-16).")
    return jurisdiction, set(hazards), facts, set(sections)


def evaluate(db_path, ruleset, payload):
    jurisdiction, hazards, facts, sections = validate_input(payload)
    if ruleset.get("review_status") != "draft_not_regulator_verified":
        raise SelectionError("Unknown rule pack review status.")
    if not Path(db_path).is_file():
        raise FileNotFoundError("Local eSDScom catalogue not installed; import your source ZIP first.")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    selected, pending, blocked = [], [], []
    try:
        for rule in ruleset["rules"]:
            if jurisdiction not in rule["jurisdictions"]:
                continue
            section = rule["section"]
            if sections and section not in sections:
                continue
            required_hazards = set(rule.get("hazards_any", []))
            if required_hazards and not (required_hazards & hazards):
                continue
            required_facts = rule.get("facts_all", [])
            missing_facts = [name for name in required_facts if facts.get(name) is not True]
            if missing_facts:
                # Only report pending checks for rules whose hazard trigger is met.
                if required_hazards:
                    pending.append({
                        "rule_id": rule["id"],
                        "section": section,
                        "reason": "Evidence must be confirmed before a phrase is suggested.",
                        "missing_facts": missing_facts,
                        "matched_hazards": sorted(required_hazards & hazards),
                    })
                continue
            # No hazard condition means a rule can fire only from verified facts.
            suffix = rule["structure_suffix"]
            code = JURISDICTION_PREFIX[jurisdiction] + "." + suffix
            rows = conn.execute(
                """SELECT entry_key, collection, structurecode, esdscom_phrase_id,
                          original_code, english, sds_section, region, source,
                          revision_date_raw, phrase_owner
                   FROM entries WHERE collection='Core' AND structurecode=?""",
                (code,),
            ).fetchall()
            if len(rows) != 1 or rows[0]["english"] != rule["expected_english"] or rows[0]["sds_section"] != section:
                blocked.append({
                    "rule_id": rule["id"],
                    "section": section,
                    "reason": "Catalogue code, section or exact wording did not match; no fallback or substitution allowed.",
                    "expected_structurecode": code,
                })
                continue
            phrase = dict(rows[0])
            selected.append({
                "rule_id": rule["id"],
                "section": section,
                "phrase": phrase["english"],
                "catalogue": phrase,
                "matched_hazards": sorted(required_hazards & hazards),
                "verified_facts": required_facts,
                "rationale": rule["rationale"],
                "rule_reference": rule["reference"],
                "review_required": True,
                "approval_status": ruleset["review_status"],
            })
    finally:
        conn.close()
    return {
        "ruleset": ruleset["id"],
        "ruleset_version": ruleset["version"],
        "catalogue_version_required": ruleset["catalogue_version"],
        "jurisdiction": jurisdiction,
        "selected": selected,
        "pending_evidence": pending,
        "blocked_matches": blocked,
        "message": "Draft candidates only. Never automatically publish these as compliant SDS text.",
    }
