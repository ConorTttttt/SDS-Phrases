"""Phase 2 regulatory requirement evaluator (stdlib only).

Regulatory rule data is *independent* of eSDScom phrase wording.
No rule pack bundled here is independently regulatory-verified.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

SCHEMA = "sds-regulatory-rules/v0.2"
JURISDICTIONS = frozenset({"EU", "GB", "US", "CA", "NZ"})
VALID_EFFECTS = frozenset({"required", "applicable"})
CODE_RE = re.compile(r"^(?:H[2-4][0-9]{2}|EUH[0-9]{3})$")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
RULE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,79}$")
UNKNOWN = "unknown"
TRUE = "yes"
FALSE = "no"


class RegulatoryError(ValueError):
    """Invalid product input or unusable rule pack."""


def _expect(condition, message):
    if not condition:
        raise RegulatoryError(message)


def _day(value, label):
    _expect(isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)),
            label + " must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RegulatoryError(label + " must be a real calendar date") from exc


def _evidenced(value):
    """Known facts require an explicit source note. No note = unknown."""
    if not isinstance(value, dict) or set(value) != {"value", "evidence"}:
        return False
    return isinstance(value["evidence"], str) and bool(value["evidence"].strip())


def validate_product(data):
    _expect(isinstance(data, dict), "Product must be a JSON object")
    _expect(data.get("jurisdiction") in JURISDICTIONS, "Unknown SDS jurisdiction")
    _day(data.get("as_of"), "as_of")
    hazards = data.get("hazards", [])
    _expect(isinstance(hazards, list) and len(hazards) <= 100, "hazards must be an array (maximum 100)")
    _expect(all(isinstance(h, str) and CODE_RE.fullmatch(h) for h in hazards),
            "hazards must contain distinct Hnnn or EUHnnn codes")
    _expect(len(set(hazards)) == len(hazards), "Duplicate hazard codes")
    completeness = data.get("classification_complete", {})
    _expect(isinstance(completeness, dict), "classification_complete must be an object")
    _expect(set(completeness) <= {"value", "evidence"}, "Invalid classification completeness fields")
    if completeness:
        _expect(completeness.get("value") in ("yes", "no", "unknown"), "classification_complete.value must be yes, no or unknown")
        _expect(isinstance(completeness.get("evidence", ""), str), "classification completeness evidence must be text")
    for key in ("facts", "attributes"):
        values = data.get(key, {})
        _expect(isinstance(values, dict) and len(values) <= 150, key + " must be an object (maximum 150 entries)")
        for name, record in values.items():
            _expect(isinstance(name, str) and KEY_RE.fullmatch(name), "Invalid " + key + " key")
            _expect(isinstance(record, dict) and set(record) == {"value", "evidence"},
                    key + "." + name + " must include value and evidence")
            _expect(isinstance(record["evidence"], str) and len(record["evidence"]) <= 1000,
                    key + "." + name + " evidence must be text (maximum 1000)")
            if key == "facts":
                _expect(record["value"] in ("yes", "no", "unknown"),
                        "Fact " + name + " must be yes, no or unknown")
            else:
                _expect(record["value"] is None or
                        (isinstance(record["value"], str) and len(record["value"]) <= 150),
                        "Attribute " + name + " must be text or null")
    return data


def _check_condition(node, depth=0):
    _expect(depth <= 8, "Rule condition nesting exceeds 8")
    _expect(isinstance(node, dict) and len(node) == 1, "Every condition must have exactly one operator")
    op, val = next(iter(node.items()))
    if op in ("all", "any"):
        _expect(isinstance(val, list) and 1 <= len(val) <= 30, op + " must have 1–30 children")
        for child in val:
            _check_condition(child, depth + 1)
    elif op == "not":
        _check_condition(val, depth + 1)
    elif op == "hazard_any":
        _expect(isinstance(val, list) and 1 <= len(val) <= 50 and
                all(isinstance(h, str) and CODE_RE.fullmatch(h) for h in val) and len(set(val)) == len(val),
                "hazard_any must have valid distinct hazard codes")
    elif op in ("fact_equals", "attribute_equals"):
        _expect(isinstance(val, dict) and set(val) == {"key", "value"}, op + " needs key and value")
        _expect(isinstance(val["key"], str) and KEY_RE.fullmatch(val["key"]), "Invalid predicate key")
        if op == "fact_equals":
            _expect(val["value"] in ("yes", "no"), "fact_equals value must be yes or no")
        else:
            _expect(isinstance(val["value"], str) and bool(val["value"]) and len(val["value"]) <= 150,
                    "attribute_equals value must be non-empty text")
    else:
        raise RegulatoryError("Unknown condition operator: " + str(op))


def validate_pack(pack):
    _expect(isinstance(pack, dict) and pack.get("schema") == SCHEMA, "Unsupported regulatory rule pack schema")
    _expect(isinstance(pack.get("id"), str) and bool(pack["id"]), "Missing pack ID")
    _expect(isinstance(pack.get("version"), str) and bool(pack["version"]), "Missing pack version")
    rules = pack.get("rules")
    _expect(isinstance(rules, list) and len(rules) <= 500, "rules must be an array (maximum 500)")
    seen = set()
    for r in rules:
        _expect(isinstance(r, dict), "Each regulatory rule must be an object")
        _expect(isinstance(r.get("id"), str) and RULE_RE.fullmatch(r["id"]), "Invalid regulatory rule ID")
        _expect(r["id"] not in seen, "Duplicate regulatory rule ID: " + r["id"])
        seen.add(r["id"])
        _expect(r.get("jurisdiction") in JURISDICTIONS, r["id"] + ": invalid jurisdiction")
        section = r.get("section")
        _expect(isinstance(section, str) and bool(re.fullmatch(r"(?:[1-9]|1[0-6])(?:\.[1-9][0-9]?)?", section)),
                r["id"] + ": invalid SDS section or subsection")
        _expect(r.get("intended_effect") in VALID_EFFECTS, r["id"] + ": unknown intended effect")
        _expect(isinstance(r.get("title"), str) and bool(r["title"].strip()), r["id"] + ": missing title")
        _check_condition(r.get("when"))
        _expect(r.get("review_status") in ("unverified", "independently_verified"),
                r["id"] + ": invalid review status")
        source = r.get("source")
        _expect(isinstance(source, dict) and
                isinstance(source.get("reference"), str) and bool(source["reference"].strip()) and
                isinstance(source.get("instrument"), str) and bool(source["instrument"].strip()) and
                isinstance(source.get("document_version"), str) and bool(source["document_version"].strip()),
                r["id"] + ": source instrument, reference and document version are required")
        start = _day(r.get("effective_from"), r["id"] + ".effective_from")
        until = r.get("effective_until")
        if until is not None:
            _expect(start <= _day(until, r["id"] + ".effective_until"), r["id"] + ": invalid effective range")
        # A mere "verified" flag is not enough: separate traceable verification is needed.
        if r["review_status"] == "independently_verified":
            v = r.get("verification")
            _expect(isinstance(v, dict) and all(isinstance(v.get(k), str) and v[k].strip()
                    for k in ("reviewer", "audit_reference", "verified_at", "source_locator")),
                    r["id"] + ": independently verified rules require reviewer, audit, date and source locator")
            _day(v["verified_at"], r["id"] + ".verification.verified_at")
            _expect(source["instrument"] != "internal_draft", r["id"] + ": internal draft cannot be legal authority")
    return pack


def _leaf(status, path, reason, missing=None, matched=None, evidence=None):
    return {"status": status, "path": path, "explanation": reason,
            "missing": missing or [], "matched_hazards": matched or [], "evidence": evidence or ""}


def _condition(node, product, path="when"):
    op, val = next(iter(node.items()))
    if op in ("all", "any"):
        children = [_condition(child, product, path + "." + op + "[" + str(i) + "]")
                    for i, child in enumerate(val)]
        states = [x["status"] for x in children]
        if op == "all":
            status = FALSE if FALSE in states else UNKNOWN if UNKNOWN in states else TRUE
        else:
            status = TRUE if TRUE in states else UNKNOWN if UNKNOWN in states else FALSE
        return {"status": status, "path": path, "operator": op, "children": children,
                "explanation": op + " conditions: " + status}
    if op == "not":
        child = _condition(val, product, path + ".not")
        status = {TRUE: FALSE, FALSE: TRUE, UNKNOWN: UNKNOWN}[child["status"]]
        return {"status": status, "path": path, "operator": "not", "children": [child],
                "explanation": "Negated condition: " + status}
    if op == "hazard_any":
        hits = sorted(set(val) & set(product["hazards"]))
        if hits:
            return _leaf(TRUE, path, "Matching classified hazard codes: " + ", ".join(hits), matched=hits)
        complete = product.get("classification_complete", {})
        if complete.get("value") == "yes" and _evidenced(complete):
            return _leaf(FALSE, path, "Hazard codes absent from a declared complete, evidenced classification",
                         evidence=complete["evidence"])
        return _leaf(UNKNOWN, path, "Absence of a hazard code cannot be established from an incomplete classification",
                     missing=["classification_complete"])
    key = val["key"]
    collection = "facts" if op == "fact_equals" else "attributes"
    record = product.get(collection, {}).get(key)
    if not record or record.get("value") in ("unknown", None) or not _evidenced(record):
        return _leaf(UNKNOWN, path, collection + "." + key + " is missing or lacks evidence",
                     missing=[collection + "." + key])
    ok = record["value"] == val["value"]
    return _leaf(TRUE if ok else FALSE, path,
                 collection + "." + key + " = " + str(record["value"]),
                 evidence=record["evidence"])


def _flatten(trace):
    nodes = [trace]
    for child in trace.get("children", []):
        nodes += _flatten(child)
    return nodes


def evaluate_evidence_condition(condition, product):
    """Public, evidence-gated condition check for non-legal authoring workflows.

    Returns a three-valued trace (yes/no/unknown). It does not certify
    conditions as legally sufficient, and never selects an SDS phrase.
    """
    validate_product(product)
    _check_condition(condition)
    return _condition(condition, product)


def evaluate_regulations(pack, product):
    """Evaluate every rule, including skipped rules, with a complete decision trace.

    Demo rules can produce candidate_unverified, never required/applicable.
    Verified status is a *data assertion*, not independent proof of a legal requirement.
    """
    validate_pack(pack)
    validate_product(product)
    results = []
    as_of = _day(product["as_of"], "as_of")
    for rule in pack["rules"]:
        outcome = {
            "rule_id": rule["id"], "title": rule["title"],
            "section": rule["section"], "jurisdiction": rule["jurisdiction"],
            "intended_effect": rule["intended_effect"], "review_status": rule["review_status"],
            "regulatory_source": rule["source"], "effective_from": rule["effective_from"],
            "effective_until": rule["effective_until"], "decision": None,
            "explanation": "", "missing_information": [], "matched_hazards": [],
            "trace": None, "publishable": False,
        }
        if product["jurisdiction"] != rule["jurisdiction"]:
            outcome["decision"] = "outside_jurisdiction"
            outcome["explanation"] = "Rule is scoped to another jurisdiction"
        elif not (_day(rule["effective_from"], "effective_from") <= as_of and
                  (not rule["effective_until"] or as_of <= _day(rule["effective_until"], "effective_until"))):
            outcome["decision"] = "outside_effective_dates"
            outcome["explanation"] = "Rule is outside its defined date interval; this does not assess other amendments"
        else:
            trace = _condition(rule["when"], product)
            outcome["trace"] = trace
            leaves = _flatten(trace)
            outcome["missing_information"] = sorted(set(
                missing for leaf in leaves for missing in leaf.get("missing", [])
            ))
            outcome["matched_hazards"] = sorted(set(
                h for leaf in leaves for h in leaf.get("matched_hazards", [])
            ))
            status = trace["status"]
            if status == UNKNOWN:
                outcome["decision"] = "information_required"
                outcome["explanation"] = "Insufficient evidence to decide condition; no phrase is selected"
            elif status == FALSE:
                outcome["decision"] = "not_triggered_unverified" if rule["review_status"] == "unverified" else "not_applicable"
                outcome["explanation"] = "Defined condition was false; this does not prove SDS completeness"
            elif rule["review_status"] != "independently_verified":
                outcome["decision"] = "candidate_unverified"
                outcome["explanation"] = "Illustrative authoring trigger only; not an asserted legal requirement"
            else:
                outcome["decision"] = rule["intended_effect"]
                outcome["explanation"] = "Verified-status rule condition matched; legal applicability still needs human approval"
        results.append(outcome)
    coverage = []
    for section in range(1, 17):
        relevant = [r for r in results if r["section"].split(".")[0] == str(section)
                    and r["jurisdiction"] == product["jurisdiction"]]
        counts = {key: sum(r["decision"] == key for r in relevant)
                  for key in ("required", "applicable", "candidate_unverified",
                              "information_required", "not_applicable", "not_triggered_unverified",
                              "outside_effective_dates")}
        coverage.append({
            "section": section, "rules_in_pack": len(relevant), "decisions": counts,
            "coverage_status": "partial_unverified" if relevant else "no_rules_in_pack",
            "is_sds_complete": False,
        })
    return {
        "engine_schema": SCHEMA, "pack_id": pack["id"], "pack_version": pack["version"],
        "product": {"jurisdiction": product["jurisdiction"], "as_of": product["as_of"]},
        "decisions": results, "coverage": coverage, "rules_evaluated": len(results),
        "sds_compliance_established": False,
        "warning": "Demo rules are not verified legislation. No output is approved SDS wording. Empty or non-triggered rules do not establish compliance.",
    }
