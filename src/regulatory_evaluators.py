"""Trusted executable evaluators bound to exact canonical requirement versions.

Controlled architecture (CLAUDE.md R9, R10):
- ``regulatory/canonical/evaluators.json`` binds a canonical requirement ID and its
  exact rule-version hash to an evaluator *name* and declarative parameters.
  The JSON never contains code: names are resolved only against ``EVALUATORS``
  below, parameters are validated per evaluator, and unknown keys are rejected.
- Three statuses stay separate: regulatory verification (read only from the
  canonical record), software implementation and runtime validation (from the
  binding).
- The R9 promotion gate is evaluated on every call. While it is closed, outputs are
  advisory and route to competent-person review; a computed outcome is never
  reported as compliant or non-compliant.
- Every call returns a reproducible decision trace with a SHA-256 digest.

Software results are not legal validation. Stdlib only; offline.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from canonical_requirements import (ROOT, all_requirements, load, load_clp, load_title_iv,
                                    read, requirement_version)
from regulatory_engine import FALSE, TRUE, UNKNOWN

REGISTRY = ROOT / "regulatory/canonical/evaluators.json"
SCHEMA = "sds-canonical-evaluators/v1"
TRACE_SCHEMA = "sds-evaluator-trace/v1"
PASS, FAIL, SUSPECT, INSUFFICIENT, NA, NOT_ASSESSED, REVIEW = (
    "Compliant against assessed requirement", "Non-compliant", "Potential non-compliance",
    "Insufficient evidence", "Not applicable", "Not assessed", "Requires competent-person review")
VERIFIED = "independently_verified_legal_rule"
SIGNOFF_FIELDS = ("competent_person", "reviewer", "audit_reference", "verified_at", "source_locator")
SOFTWARE_STATUSES = frozenset({"pilot_implemented"})
RUNTIME_STATUSES = frozenset({"regression_tested", "not_tested"})
BINDING_KEYS = frozenset({"requirement_id", "rule_version", "evaluator", "evaluator_version", "parameters",
                          "software_implementation_status", "runtime_validation", "limitations"})
UNITS = {"weight": "% w/w", "volume": "% v/v"}
SUPPORTED_UNITS = frozenset(UNITS.values())
THRESHOLD_TEXT = re.compile(r"(≥|>|≤|<) (\d+(?:,\d+)?) % by (weight|volume)")
OPERATORS = {"≥": ">=", ">": ">", "≤": "<=", "<": "<"}
FLAG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class EvaluatorError(ValueError):
    """Invalid evaluator registry, binding or input structure."""


def _require(condition, message):
    if not condition:
        raise EvaluatorError(message)


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- input primitives

def fact(record, key, allowed=(TRUE, FALSE)):
    """Evidenced three-valued fact: {"value": ..., "evidence": "..."}; anything else is unknown."""
    v = record.get(key) if isinstance(record, dict) else None
    if not isinstance(v, dict) or not isinstance(v.get("evidence"), str) or not v["evidence"].strip():
        return UNKNOWN, None
    return (v.get("value"), v["evidence"]) if v.get("value") in allowed else (UNKNOWN, v["evidence"])


def decimal(value, label):
    """Exact decimal from a string or integer; floats are rejected to avoid binary rounding."""
    _require(type(value) in (str, int), label + " must be a decimal string or integer, not " + type(value).__name__)
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation as exc:
        raise EvaluatorError(label + " is not a decimal number") from exc
    _require(number.is_finite(), label + " must be finite")
    return number


def quantity(record, label):
    """Concentration as a point {"value"} or interval {"low","high"} with unit and evidence.

    Returns (low, high, unit, evidence, low_inclusive, high_inclusive) or None if missing.
    """
    if not isinstance(record, dict):
        return None
    evidence = record.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        return None
    unit = record.get("unit")
    _require(isinstance(unit, str) and unit.strip(), label + " requires a unit")
    if "value" in record:
        _require(not ({"low", "high"} & set(record)), label + ": give a value or an interval, not both")
        low = high = decimal(record["value"], label + ".value")
        inc = (True, True)
    else:
        _require("low" in record and "high" in record, label + " requires value or low/high")
        low, high = decimal(record["low"], label + ".low"), decimal(record["high"], label + ".high")
        _require(low <= high, label + ": interval low exceeds high")
        inc = (record.get("low_inclusive", True), record.get("high_inclusive", True))
        _require(all(type(x) is bool for x in inc), label + ": inclusivity flags must be boolean")
        _require(low < high or all(inc), label + ": empty interval")
    if unit in SUPPORTED_UNITS:
        _require(Decimal(0) <= low and high <= Decimal(100), label + ": percentage outside 0–100")
    return low, high, unit, evidence, inc[0], inc[1]


def compare_interval(q, operator, threshold, unit):
    """Three-valued comparison of a concentration (point or interval) with a threshold."""
    low, high, given_unit, _, low_inc, high_inc = q
    if given_unit != unit:
        return UNKNOWN, (f"Unit {given_unit} differs from required {unit}; no conversion is performed "
                         "(density or molar data and an approved method would be required)")
    def holds(x, inclusive_edge):
        if operator == ">=":
            return x >= threshold if inclusive_edge or x != threshold else False
        if operator == ">":
            return x > threshold
        if operator == "<=":
            return x <= threshold if inclusive_edge or x != threshold else False
        return x < threshold
    lo, hi = holds(low, low_inc), holds(high, high_inc)
    if lo and hi:
        return TRUE, "Entire reported concentration satisfies the threshold"
    if not lo and not hi:
        return FALSE, "Entire reported concentration is outside the threshold"
    return UNKNOWN, "Reported concentration interval straddles the threshold; the exact value is required"


def all3(states):
    return FALSE if FALSE in states else UNKNOWN if UNKNOWN in states else TRUE


def any3(states):
    return TRUE if TRUE in states else UNKNOWN if UNKNOWN in states else FALSE


class Trace:
    """Collects conditions, evidence, calculations and missing information."""

    def __init__(self, inputs):
        self.inputs, self.conditions, self.evidence = inputs, [], []
        self.calculations, self.missing, self.contradictions, self.notes = [], [], [], []

    def fact(self, key, expected=TRUE, allowed=(TRUE, FALSE), label=None):
        value, evidence = fact(self.inputs, key, allowed)
        if value == UNKNOWN:
            self.missing.append(key)
            state = UNKNOWN
        else:
            self.evidence.append({"input": key, "evidence": evidence})
            state = TRUE if (value in expected if isinstance(expected, tuple) else value == expected) else FALSE
        self.conditions.append({"condition": label or f"{key} == {expected}", "input": key,
                                "observed": value, "result": state})
        return state, value


# ---------------------------------------------------------------- evaluators

def _check_params(params, allowed):
    _require(isinstance(params, dict), "parameters must be an object")
    unknown = set(params) - set(allowed)
    _require(not unknown, "Unknown evaluator parameters: " + ", ".join(sorted(unknown)))
    for key, kind in allowed.items():
        _require(key in params, "Missing evaluator parameter " + key)
        _require(isinstance(params[key], kind), "Invalid type for parameter " + key)


def _threshold_spec(spec, wording, label):
    """A threshold must be copied verbatim from the canonical wording (R7)."""
    _check_params(spec, {"source_text": str, "operator": str, "value": str, "unit": str})
    _require(spec["source_text"] in wording, label + ": threshold source text not found in canonical wording")
    match = THRESHOLD_TEXT.fullmatch(spec["source_text"])
    _require(match is not None, label + ": unsupported threshold wording")
    op, number, basis = match.groups()
    _require(OPERATORS[op] == spec["operator"], label + ": operator differs from source text")
    _require(Decimal(number.replace(",", ".")) == decimal(spec["value"], label), label + ": value differs from source text")
    _require(UNITS[basis] == spec["unit"], label + ": unit differs from source text")
    return OPERATORS[op], decimal(spec["value"], label), spec["unit"]


def _hazard_contradiction(t):
    """Classified-hazardous claim against an evidenced complete classification without hazard codes."""
    hazardous, _ = fact(t.inputs, "hazardous")
    complete, _ = fact(t.inputs, "classification_complete")
    codes = t.inputs.get("hazard_codes")
    if isinstance(codes, list) and complete == TRUE:
        if hazardous == TRUE and not codes:
            t.contradictions.append("hazardous = yes but an evidenced complete classification lists no hazard codes")
        if hazardous == FALSE and codes:
            t.contradictions.append("hazardous = no but an evidenced complete classification lists hazard codes")


def _scope(t, kinds):
    scope, _ = t.fact("title_iv_in_scope", label="REACH Title IV scope evidenced (Article 2 resolved by user)")
    kind_state, kind = t.fact("product_type", expected=kinds, allowed=("substance", "mixture"),
                              label="product_type in " + "/".join(kinds))
    return scope, kind_state, kind


def validate_article31_1(params, record):
    _check_params(params, {"branch": str})
    _require(params["branch"] in ("hazardous", "pbt_vpvb", "candidate_list_other_reason"), "Unknown Article 31(1) branch")


def run_article31_1(params, t, record):
    branch = params["branch"]
    _hazard_contradiction(t)
    kinds = ("substance", "mixture") if branch == "hazardous" else ("substance",)
    scope, kind_state, _ = _scope(t, kinds)
    trigger, _ = t.fact(branch, label=f"{branch} == yes (evidenced)")
    outcome = all3([scope, kind_state, trigger])
    t.calculations.append({"name": "article31_1_" + branch + "_trigger", "result": outcome})
    if outcome == FALSE:
        t.notes.append("This branch is not indicated. Other Article 31(1)/(3) branches and Article 32 still require assessment.")
    return outcome, {"yes": "SDS supply trigger indicated for this branch", "no": "Branch not indicated",
                     "unknown": "Trigger cannot be determined from evidenced inputs"}[outcome]


def validate_article31_4(params, record):
    _check_params(params, {})


def run_article31_4(params, t, record):
    _hazard_contradiction(t)
    hazardous, _ = t.fact("hazardous", label="hazardous substance or mixture")
    public, _ = t.fact("offered_or_sold_to_general_public")
    sufficient, _ = t.fact("public_safety_information_sufficient",
                           label="sufficient information provided to users (competent-person judgement)")
    request, _ = t.fact("downstream_user_or_distributor_request", expected=FALSE,
                        label="no downstream user or distributor request")
    outcome = all3([hazardous, public, sufficient, request])
    t.calculations.append({"name": "article31_4_exception_conditions", "result": outcome})
    t.notes.append("Sufficiency of public information is a competent-person judgement; it is never inferred.")
    return outcome, {"yes": "Article 31(4) exception conditions indicated", "no": "Exception conditions not met",
                     "unknown": "Exception conditions cannot be determined"}[outcome]


def validate_article31_3(params, record):
    _check_params(params, {"ingredient_flag": str, "phase_thresholds": dict})
    _require(FLAG_RE.fullmatch(params["ingredient_flag"]), "Invalid ingredient flag name")
    phases = params["phase_thresholds"]
    _require(phases and set(phases) <= {"non_gaseous", "gaseous"}, "phase_thresholds keys must be non_gaseous/gaseous")
    for phase, spec in phases.items():
        _threshold_spec(spec, record["wording"], phase)


def run_article31_3(params, t, record):
    _hazard_contradiction(t)
    flag = params["ingredient_flag"]
    _, kind_state, _ = _scope(t, ("mixture",))
    unclassified, _ = t.fact("hazardous", expected=FALSE, label="mixture does not meet classification criteria")
    request, _ = t.fact("recipient_request", label="recipient requested an SDS")
    phase_state, phase = t.fact("mixture_phase", expected=("non_gaseous", "gaseous"),
                                allowed=("non_gaseous", "gaseous"), label="mixture phase evidenced")
    contains = UNKNOWN
    if phase in ("non_gaseous", "gaseous"):
        if phase not in params["phase_thresholds"]:
            t.notes.append(f"No automatic conclusion for {phase} mixtures under this branch.")
            t.missing.append("approved threshold for " + phase + " mixtures (none in this branch)")
        else:
            op, threshold, unit = _threshold_spec(params["phase_thresholds"][phase], record["wording"], phase)
            contains = _ingredients(t, flag, op, threshold, unit)
    outcome = all3([kind_state, unclassified, request, phase_state, contains])
    t.calculations.append({"name": "article31_3_request_trigger", "ingredient_flag": flag, "result": outcome})
    return outcome, {"yes": "Article 31(3) on-request trigger indicated", "no": "Trigger not indicated",
                     "unknown": "Trigger cannot be determined from evidenced inputs"}[outcome]


def _ingredients(t, flag, op, threshold, unit):
    items = t.inputs.get("ingredients")
    if not isinstance(items, list) or not items:
        t.missing.append("ingredients")
        return UNKNOWN
    states, seen, totals = [], {}, {}
    for i, item in enumerate(items):
        _require(isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip(),
                 f"ingredients[{i}] requires an id")
        key = canonical_json(item)
        if item["id"] in seen and seen[item["id"]] != key:
            t.contradictions.append(f"Ingredient {item['id']} is reported twice with different data")
        seen[item["id"]] = key
        q = quantity(item.get("concentration"), f"ingredients[{i}].concentration")
        flag_state, flag_evidence = fact(item.get("flags", {}), flag)
        calc = {"ingredient": item["id"], "flag": flag, "flag_value": flag_state,
                "threshold": f"{op} {threshold} {unit}"}
        if flag_evidence:
            t.evidence.append({"input": f"ingredients[{item['id']}].flags.{flag}", "evidence": flag_evidence})
        if q is None:
            t.missing.append(f"ingredients[{item['id']}].concentration")
            conc_state, reason = UNKNOWN, "Concentration missing or unevidenced"
        else:
            low, high, given, evidence, *_ = q
            t.evidence.append({"input": f"ingredients[{item['id']}].concentration", "evidence": evidence})
            calc["concentration"] = {"low": str(low), "high": str(high), "unit": given}
            conc_state, reason = compare_interval(q, op, threshold, unit)
            totals.setdefault(given, Decimal(0))
            totals[given] += low
        if flag_state == UNKNOWN:
            t.missing.append(f"ingredients[{item['id']}].flags.{flag}")
        state = all3([TRUE if flag_state == TRUE else FALSE if flag_state == FALSE else UNKNOWN, conc_state])
        calc.update(concentration_result=conc_state, reason=reason, result=state)
        t.calculations.append(calc)
        states.append(state)
    for given, total in totals.items():
        if given in SUPPORTED_UNITS and total > Decimal(100):
            t.contradictions.append(f"Sum of minimum ingredient concentrations exceeds 100 {given} ({total})")
    result = any3(states)
    if result == FALSE:
        complete, _ = t.fact("composition_complete", label="evidenced complete composition (needed to conclude absence)")
        if complete != TRUE:
            result = UNKNOWN
            t.notes.append("No listed ingredient meets the threshold, but absence cannot be concluded without an evidenced complete composition.")
    return result


def validate_structure(params, record):
    _check_params(params, {"check": str})
    _require(params["check"] in ("main_headings", "no_blank_subsections"), "Unknown structural check")


def run_structure(params, t, record):
    from reach_annex2_audit import ReachAuditError, audit_structure
    structure = t.inputs.get("structure")
    if not isinstance(structure, dict):
        t.missing.append("structure")
        return UNKNOWN, "No heading inventory supplied"
    profile = dict(structure, jurisdiction="EU", as_of=t.inputs.get("as_of"),
                   product_type=t.inputs.get("product_type", {"value": "unknown", "evidence": ""}))
    try:
        audit = audit_structure(profile)
    except ReachAuditError as exc:
        raise EvaluatorError("Invalid heading inventory: " + str(exc)) from exc
    evidence = structure.get("inventory_complete", {}).get("evidence", "")
    if audit["inventory_complete_evidenced"]:
        t.evidence.append({"input": "structure.inventory_complete", "evidence": evidence})
    else:
        t.missing.append("structure.inventory_complete (evidenced yes)")
    if params["check"] == "main_headings":
        main = [o for o in audit["outcomes"] if "." not in o["code"]]
        states = [TRUE if o["decision"] == "reported_present" else FALSE if o["decision"] == "reported_missing"
                  else UNKNOWN for o in main]
        for o, s in zip(main, states):
            t.conditions.append({"condition": f"heading {o['code']} present", "input": "structure.headings",
                                 "observed": o["decision"], "result": s})
        outcome = all3(states)
        t.calculations.append({"name": "main_headings_present", "present": states.count(TRUE),
                               "missing": states.count(FALSE), "undetermined": states.count(UNKNOWN), "result": outcome})
        return outcome, {"yes": "All 16 main headings reported", "no": "Required main heading(s) reported missing",
                         "unknown": "Main headings cannot be established"}[outcome]
    blanks = [o["code"] for o in audit["outcomes"] if o["decision"] == "reported_blank"]
    outcome = FALSE if blanks else TRUE if audit["inventory_complete_evidenced"] else UNKNOWN
    t.conditions.append({"condition": "no blank subsections", "input": "structure.blank_subsections",
                         "observed": blanks, "result": outcome})
    t.calculations.append({"name": "blank_subsections", "blank": blanks, "result": outcome})
    return outcome, {"yes": "No blank subsections in an evidenced complete inventory",
                     "no": "Blank subsection(s) reported: " + ", ".join(blanks),
                     "unknown": "Blank subsections cannot be excluded"}[outcome]


def validate_dated(params, record):
    _check_params(params, {})


def run_dated(params, t, record):
    value = t.inputs.get("sds_date")
    if not isinstance(value, dict) or not isinstance(value.get("evidence"), str) or not value["evidence"].strip():
        t.missing.append("sds_date")
        t.conditions.append({"condition": "SDS date evidenced", "input": "sds_date", "observed": None, "result": UNKNOWN})
        return UNKNOWN, "SDS date not evidenced"
    if value.get("value") == "absent":
        state = FALSE
    else:
        try:
            date.fromisoformat(value.get("value"))
            state = TRUE
        except (TypeError, ValueError) as exc:
            raise EvaluatorError("sds_date must be an ISO date or 'absent'") from exc
    t.evidence.append({"input": "sds_date", "evidence": value["evidence"]})
    t.conditions.append({"condition": "SDS bears a date", "input": "sds_date", "observed": value.get("value"), "result": state})
    t.calculations.append({"name": "sds_dated", "result": state})
    return state, "SDS date reported" if state == TRUE else "SDS reported undated"


class Evaluator:
    def __init__(self, version, validate, run, determinative):
        self.version, self.validate, self.run = version, validate, run
        # Status used only when the promotion gate is open, per computed outcome.
        self.determinative = determinative


OBLIGATION = {TRUE: REVIEW, FALSE: REVIEW}
CONFORMITY = {TRUE: PASS, FALSE: FAIL}
EVALUATORS = {
    "article31_1_trigger": Evaluator("1.0.0", validate_article31_1, run_article31_1, OBLIGATION),
    "article31_4_public_exception": Evaluator("1.0.0", validate_article31_4, run_article31_4, OBLIGATION),
    "article31_3_ingredient_threshold": Evaluator("1.0.0", validate_article31_3, run_article31_3, OBLIGATION),
    "annex_ii_structure": Evaluator("1.0.0", validate_structure, run_structure, CONFORMITY),
    "sds_dated": Evaluator("1.0.0", validate_dated, run_dated, CONFORMITY),
}


# ---------------------------------------------------------------- registry

_CACHE = {}
_INPUTS = ("regulatory/canonical/requirements.json", "regulatory/canonical/title_iv.json", "regulatory/canonical/clp.json",
           "regulatory/assessment/annex_ii.json", "regulatory/source_manifest.json")


def _stamp(root, names):
    out = []
    for name in names:
        path = Path(root) / name
        st = path.stat() if path.exists() else None
        out.append((str(path.resolve()), st.st_mtime_ns if st else None, st.st_size if st else None))
    return tuple(out)


def _components(root):
    """Validated canonical components, cached by file path, mtime and size (read-only use)."""
    key = ("components", _stamp(root, _INPUTS))
    if key not in _CACHE:
        _CACHE[key] = _load_components(root)
    return _CACHE[key]


def _load_components(root):
    pack, _, sources = load(root)
    title = load_title_iv(root, pack)
    clp = load_clp(root, pack, title)
    current = {r["id"]: r for r in all_requirements(root)}
    historical = {}
    for comp in (pack, title, clp):
        for h in comp.get("historical_versions", []):
            historical[(h["record"]["id"], requirement_version(h["record"]))] = h["record"]
    shas = {"title_iv": title["source_sha256"], "clp": clp["source_sha256"]}
    return current, historical, sources, shas


def validate_registry(registry, root=ROOT):
    """Validate a binding registry; raise EvaluatorError on any unsafe or inconsistent entry."""
    _require(isinstance(registry, dict) and registry.get("schema") == SCHEMA, "Unsupported evaluator registry schema")
    _require(set(registry) == {"schema", "registry_version", "description", "bindings"}, "Unexpected registry keys")
    _require(isinstance(registry["registry_version"], str) and registry["registry_version"].strip(), "Missing registry version")
    current, historical, _, _ = _components(root)
    seen = set()
    bindings = registry["bindings"]
    _require(isinstance(bindings, list), "bindings must be an array")
    for b in bindings:
        _require(isinstance(b, dict), "Binding must be an object")
        extra = set(b) - BINDING_KEYS
        _require(not extra, "Binding contains forbidden or unknown keys: " + ", ".join(sorted(extra)))
        _require(BINDING_KEYS <= set(b), "Binding is missing required keys")
        rid, version = b["requirement_id"], b["rule_version"]
        _require((rid, version) not in seen, "Duplicate binding " + rid)
        seen.add((rid, version))
        record = current.get(rid) if current.get(rid) and requirement_version(current[rid]) == version else historical.get((rid, version))
        _require(record is not None, f"{rid}: rule version {version} is neither current nor archived")
        evaluator = EVALUATORS.get(b["evaluator"]) if isinstance(b["evaluator"], str) else None
        _require(evaluator is not None, f"{rid}: evaluator {b['evaluator']!r} is not an approved implementation")
        _require(b["evaluator_version"] == evaluator.version, f"{rid}: evaluator version mismatch")
        _require(b["software_implementation_status"] in SOFTWARE_STATUSES, f"{rid}: invalid software implementation status")
        runtime = b["runtime_validation"]
        _require(isinstance(runtime, dict) and set(runtime) == {"status", "tests"} and runtime["status"] in RUNTIME_STATUSES
                 and isinstance(runtime["tests"], list) and all(isinstance(x, str) and (root / x).is_file() for x in runtime["tests"]),
                 f"{rid}: runtime validation must name a status and existing test files")
        _require(isinstance(b["limitations"], list) and all(isinstance(x, str) and x.strip() for x in b["limitations"]),
                 f"{rid}: limitations must be text")
        evaluator.validate(b["parameters"], record)
    return registry


def load_registry(root=ROOT, path=None):
    path = Path(path) if path else Path(root) / "regulatory/canonical/evaluators.json"
    key = ("registry", str(Path(root).resolve()), _stamp(root, _INPUTS), _stamp(path.parent, [path.name]))
    if key not in _CACHE:
        _CACHE[key] = validate_registry(read(path), root)
    return copy.deepcopy(_CACHE[key])


def _trusted(registry, root):
    """Every registry object is validated before use, including ones passed in by callers."""
    if registry is None:
        return load_registry(root)
    key = ("validated", str(Path(root).resolve()), sha(registry), _stamp(root, _INPUTS))
    if key not in _CACHE:
        _CACHE[key] = validate_registry(copy.deepcopy(registry), root)
    return _CACHE[key]


def bindings_for(registry):
    return {(b["requirement_id"], b["rule_version"]): b for b in registry["bindings"]}


# ---------------------------------------------------------------- gate and evaluation

def promotion_gate(record, source):
    """R9 gate. Opens only for an independently verified rule with complete competent-person sign-off
    and a source whose currentness has been verified. The canonical loader additionally refuses any
    on-disk record that is not manual_review_only, so no committed record can open it today."""
    reasons = []
    if record.get("verification_status") != VERIFIED:
        reasons.append("Regulatory verification status is " + str(record.get("verification_status")))
    signoff = record.get("regulatory_signoff")
    if not (isinstance(signoff, dict) and all(isinstance(signoff.get(k), str) and signoff[k].strip() for k in SIGNOFF_FIELDS)):
        reasons.append("No complete competent-person sign-off recorded (" + ", ".join(SIGNOFF_FIELDS) + ")")
    else:
        try:
            date.fromisoformat(signoff["verified_at"])
        except ValueError:
            reasons.append("Sign-off date is invalid")
    if not source or source.get("currentness") != "verified_current_for_assessment_date":
        reasons.append("Source currentness after the snapshot is not verified")
    return {"open": not reasons, "reasons": reasons}


def _source(record, sources, shas):
    src = sources.get(record.get("source_id"))
    if src is None or src.get("version") != record.get("source_version"):
        return None, "Legal source not registered in the pinned manifest for this version"
    component = "title_iv" if record["id"].startswith("EU-REACH-A") and not record["id"].startswith("EU-REACH-AII") else \
        "clp" if record["id"].startswith("EU-CLP") else None
    if component and shas.get(component) != src["sha256"]:
        return None, "Component source hash differs from the pinned manifest"
    return src, None


def evaluate(requirement_id, inputs, registry=None, root=ROOT, rule_version=None, record=None):
    """Run the approved evaluator bound to the exact rule version and return a decision trace."""
    registry = _trusted(registry, root)
    current, historical, sources, shas = _components(root)
    if record is None:
        record = current.get(requirement_id)
        if rule_version and record is not None and requirement_version(record) != rule_version:
            record = historical.get((requirement_id, rule_version))
    _require(isinstance(inputs, dict), "Evaluator inputs must be an object")
    version = requirement_version(record) if record else rule_version
    binding = bindings_for(registry).get((requirement_id, version))
    trace = Trace(inputs)
    limitations, citations, outcome, explanation, status = [], [], UNKNOWN, "", NOT_ASSESSED
    gate = {"open": False, "reasons": ["Not evaluated"]}
    if record is None:
        explanation = "Unknown requirement or unsupported rule version"
    elif binding is None:
        explanation = ("No approved evaluator for this exact rule version; manual review required"
                       if any(k[0] == requirement_id for k in bindings_for(registry)) else
                       "No approved evaluator; manual review required")
        status = REVIEW
    else:
        src, problem = _source(record, sources, shas)
        citations.append({"requirement_id": record["id"], "clause": record["clause"], "source_id": record["source_id"],
                          "source_version": record["source_version"], "source_sha256": src["sha256"] if src else None,
                          "pdf_pages": record["pdf_pages"], "printed_pages": record["printed_pages"],
                          "legal_authority_type": record["legal_authority_type"], "wording": record["wording"]})
        gate = promotion_gate(record, src)
        limitations += list(binding["limitations"])
        limitations += ["Exceptions to review: " + x for x in record.get("exceptions", [])]
        if record.get("transition_rules"):
            limitations.append("Transition rules: " + record["transition_rules"])
        as_of = inputs.get("as_of")
        try:
            when = date.fromisoformat(as_of) if isinstance(as_of, str) else None
        except ValueError as exc:
            raise EvaluatorError("as_of must be YYYY-MM-DD") from exc
        if problem:
            explanation = problem + "; evaluator not executed"
        elif inputs.get("jurisdiction") not in (None, "EU"):
            explanation = "Only EU determinations are supported"
        elif when is None:
            trace.missing.append("as_of")
            explanation, status = "Assessment date missing; temporal applicability unknown", INSUFFICIENT
        elif record.get("effective_date") and when < date.fromisoformat(record["effective_date"]):
            explanation = f"Assessment date precedes effective date {record['effective_date']}; earlier law applies"
        else:
            if not record.get("effective_date"):
                limitations.append("Effective date of this candidate is unresolved in the canonical registry; temporal applicability requires review")
            if src and as_of != src["version"]:
                limitations.append(f"Assessment date differs from the {src['version']} consolidation; amendments must be checked")
            limitations.append("Source currentness: " + (src or {}).get("currentness", "unknown"))
            outcome, explanation = EVALUATORS[binding["evaluator"]].run(binding["parameters"], trace, record)
            if trace.contradictions:
                status = REVIEW
                outcome = UNKNOWN
                explanation = "Contradictory inputs: " + "; ".join(trace.contradictions)
            elif outcome == UNKNOWN:
                status = INSUFFICIENT
            elif gate["open"]:
                status = EVALUATORS[binding["evaluator"]].determinative[outcome]
            else:
                status = REVIEW
    used = sorted({c["input"] for c in trace.conditions if c.get("input")} |
                  {e["input"].split("[")[0].split(".")[0] for e in trace.evidence} | {"as_of", "jurisdiction"})
    data = {k: inputs[k] for k in used if k in inputs}
    out = {
        "schema": TRACE_SCHEMA,
        "requirement_id": requirement_id,
        "rule_version": version,
        "evaluator": binding["evaluator"] if binding else None,
        "evaluator_version": binding["evaluator_version"] if binding else None,
        "registry_version": registry["registry_version"],
        "binding_digest": sha(binding) if binding else None,
        "input_data": data,
        "input_digest": sha(data),
        "evidence_references": trace.evidence,
        "evaluated_conditions": trace.conditions,
        "regulatory_citations": citations,
        "calculation_results": trace.calculations,
        "missing_information": sorted(set(trace.missing)),
        "contradictions": trace.contradictions,
        "outcome": outcome,
        "explanation": explanation,
        "notes": trace.notes,
        "assessment_status": status,
        "verification": {
            "regulatory_verification_status": record.get("verification_status") if record else None,
            "canonical_implementation_status": record.get("implementation_status") if record else None,
            "software_implementation_status": binding["software_implementation_status"] if binding else "not_implemented",
            "runtime_validation_status": binding["runtime_validation"]["status"] if binding else "not_tested",
            "promotion_gate": gate,
        },
        "decision_effect": ("determinative_subject_to_competent_person_release" if gate["open"] and status in (PASS, FAIL)
                            else "advisory_pending_regulatory_verification"),
        "limitations": limitations + ["Software evaluation is not legal or regulatory validation; competent-person release required"],
        "legal_compliance_determined": False,
    }
    out["trace_digest"] = sha(out)
    return out


def verify_trace(trace):
    """Recompute the trace digest (tamper and reproducibility check)."""
    body = {k: v for k, v in trace.items() if k != "trace_digest"}
    return sha(body) == trace.get("trace_digest")


def evaluate_record(record, registry=None, root=ROOT):
    """Evaluate every current binding against one product record (toolkit input format)."""
    registry = _trusted(registry, root)
    current = _components(root)[0]
    results = []
    for b in registry["bindings"]:
        r = current.get(b["requirement_id"])
        if r is not None and requirement_version(r) == b["rule_version"]:
            results.append(evaluate(b["requirement_id"], record, registry, root))
    return results


def calculation_summary(trace):
    """Structured, export-safe calculation record for the Gemini exchange (no free-form inputs)."""
    return canonical_json({k: trace[k] for k in (
        "requirement_id", "rule_version", "evaluator", "evaluator_version", "registry_version", "outcome",
        "assessment_status", "decision_effect", "calculation_results", "missing_information", "contradictions",
        "input_digest", "trace_digest")} | {"promotion_gate_open": trace["verification"]["promotion_gate"]["open"]})


def registry_coverage(registry=None, root=ROOT):
    registry = _trusted(registry, root)
    current = _components(root)[0]
    bound = {b["requirement_id"]: b for b in registry["bindings"]
             if b["requirement_id"] in current and requirement_version(current[b["requirement_id"]]) == b["rule_version"]}
    return {"registry_version": registry["registry_version"], "candidate_targets": len(current),
            "bound_to_executable_evaluator": len(bound), "manual_review_only": len(current) - len(bound),
            "promotion_gate_open": 0, "bindings": sorted(bound)}
